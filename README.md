# Android native library merging

## The Problem

Android developers who use lots of C++ code
might be familiar with the [native library limit][the_limit]
that exists in Android versions prior to 4.3.
When targeting older Android versions,
one must carefully manage the number of libraries in their app
to avoid hitting this limit.
This is especially tricky because
libraries loaded by the system count against this limit,
and the number of those libraries can vary between devices.

[the_limit]: https://android.googlesource.com/platform/bionic/+/ba98d9237b0eabc1d8caf2600fd787b988645249%5E%21/

One solution is to
manually combine multiple small libraries into one larger one.
However, this usually is not a scalable solution.
Combining libraries requires moving source code around
and carefully managing compilation settings and dependencies.
It can also make code less modular,
which can be problematic
if your organization is building multiple apps from a shared codebase.

## Our Solution

We have developed a more scalable solution to this problem
and applied it to most of our Android apps,
including Facebook,
Instagram,
Messenger,
Messenger Lite,
Moments,
and Pages Manager.
This solution not only allows us to
avoid the native library limit on older Android devices,
but it does so without harming performance or increasing app size.

### Merging Objects with Per-App Configuration

The first part of the solution is to
combine multiple native libraries.
Because merging shared objects (`.so` files) is impractical,
we needed to change the way we link our libraries,
which forced us to integrate this feature into our build system
[Buck](https://buckbuild.com/).
The [feature](https://github.com/facebook/buck/commit/7b7bc87e)
allows each application to specify which libraries should be merged
so they can avoid accidentally bringing in unnecessary dependencies.
Buck then takes care of
collecting all the objects (`.o` files) for each merged library
and linking them together with the proper dependencies.

This works great, as long as
there are no common symbols between the libraries being merged.
For example, pure C++ libraries rarely duplicate symbols.
However, on Android, many of our libraries use JNI,
which means they have exactly one symbol that is duplicated: `JNI_OnLoad`.
This is the entry point for JNI setup in the library,
and almost all of our libraries define it.

Since we have issues with only this one duplicate symbol,
we handle it in a special way.

### Merging JNI_OnLoad

The first step in eliminating the symbol conflict is to
make each library rename its `JNI_OnLoad` function.
This is easy enough with the C preprocessor.
Next, we need a way to find all of those renamed functions
so we can call them at the appropriate time.
We accomplish this with custom ELF sections.
(There's a good description on [this blog][custom_elf].)
In short, each JNI library to be merged defines a small registration object
that includes the library name and a pointer to its `JNI_OnLoad`.
Then the linker will automatically concatenate them into an array
and define a pair of symbols that we can use to find them.

[custom_elf]: http://mgalgs.github.io/2013/05/10/hacking-your-ELF-for-fun-and-profit.html

Once all the `JNI_OnLoad` function pointers are
paired with their library names and placed in an array,
our glue code can find and call them
when we try to load the original libraries.

### Loading the libraries

We want our Java code to continue loading libraries by their original names,
because different libraries might be merged in different apps.
Therefore, we need to wrap all of our `System.loadLibrary` calls
with a method that knows how to
map the original library names to the merged names.
Fortunately, our apps already use
[SoLoader](https://github.com/facebook/SoLoader),
so all we had to do was generate some code
to let SoLoader look up the proper merged library names.
When it first loads a merged native library,
we call a custom `JNI_OnLoad` that
registers each of the original `JNI_OnLoad` function pointers
as normal JNI methods.
Then, `SoLoader` is able to call those methods
only when the original library is loaded.
This prevents us from loading classes earlier than we should.

### Extra challenges

When implementing this native library merging strategy,
we ran into a few unexpected problems.

Some libraries might be merged in one app but not in another.
In theory, this should be fine:
We define `JNI_OnLoad` as a weak symbol
that is replaced by our special merge-aware `JNI_OnLoad`
only if we end up merging that library.
However, older versions of Android
will refuse to return any weak symbol when calling `dlopen`.
We got around this by changing the name to `JNI_OnLoad_Weak`,
then using linker flags to define `JNI_OnLoad` as a strong alias
for whichever `JNI_OnLoad_Weak` ends up being used.

When using custom ELF sections, the `gold` linker always
outputs the special `__start` and `__end` symbols as
[global symbols][gold_global].
This is not a problem when producing a single merged library,
but when there are multiple libraries,
they can end up pointing to each other's custom sections,
which breaks registration.
Declaring the references to these symbols as hidden
takes precedence over the linker-generaged global symbols,
so the symbols become hidden and the problem goes away.

[gold_global]: https://sourceware.org/git/gitweb.cgi?p=binutils-gdb.git;a=blob;f=gold/layout.cc;hb=refs/tags/binutils-2_29_1.1#l2186

## Putting it all together

We have published a repository that serves as a demonstration of these techniques.
First, take a look at
[`refs/heads/initial-code`](https://github.com/fbsamples/android-native-library-merging-demo/commit/initial-code).
This is a small codebase showing two apps that have some shared code.

![dependency graph](https://github.com/fbsamples/android-native-library-merging-demo/blob/master/images/dep-graph.png)

[`refs/heads/add-jni`](https://github.com/fbsamples/android-native-library-merging-demo/commit/add-jni)
replaces some of the Java code
(really just some string constants)
with JNI.
Now each of the apps has a few native libraries in it.

[`refs/heads/merge-libraries`](https://github.com/fbsamples/android-native-library-merging-demo/commit/merge-libraries)
is where we turn everything on.
Let's walk through it file by file.

[`bucklets/DEFS`](https://github.com/fbsamples/android-native-library-merging-demo/blob/master/bucklets/DEFS)
defines some wrappers for our build rules.
This is Buck's main mechanism for extension.
It allows expanding one declared rule into multiple physical rules,
or (in our case) modifying arguments to a rule.
We define two wrappers.
The `my_android_binary` wrapper
automatically applies our project-specific configuration
(glue library, code generator, and symbols to make local)
whenever a merge map is present.
The `my_cxx_library` wrapper adds the `allow_jni_merging` flag
as a shorthand for the tweaks we need to make to `JNI_OnLoad`.
Note that these tweaks are safe
even if the library won't be merged in all apps.

The changes to the existing code are fairly simple.
We just apply `allow_jni_merging` to our C++
and change `System.loadLibrary` to `SoLoader.loadLibrary`.

[`src/com/facebook/soloader`](https://github.com/fbsamples/android-native-library-merging-demo/tree/master/src/com/facebook/soloader)
is a simplified version of `SoLoader`
that has support only for remapping merged library names.
It also includes `MergedSoMapping`,
a compilation stub
that can also be used in apps that don't use merging.

[`map_code_generator.py`](https://github.com/fbsamples/android-native-library-merging-demo/blob/master/src/com/facebook/jnimerge/map_code_generator.py)
is the code generator that will
convert the text version of the merged library map
into Java code we can use to load the libraries at runtime.
It produces a method, `mapLibName`,
that can report which libraries were merged.
For example, `mapLibName("libanimals.so")` will return `"libeverything.so"`.
It produces a nested class, `Invoke_JNI_OnLoad`,
with a number of native methods.
Our glue code will bind each one of these to
one of the original (pre-merged) `JNI_OnLoad` function pointers.
Finally, it produces `invokeJniOnload`,
which can invoke the proper `JNI_OnLoad` for a given library, by name.
The generated code is used only by SoLoader.

[`jni_lib_merge.h`](https://github.com/fbsamples/android-native-library-merging-demo/blob/master/src/com/facebook/jnimerge/jni_lib_merge.h)
is included in our C++ files automatically
(because we added `allow_jni_merging`).
It uses the C preprocessor to wrap `JNI_OnLoad`,
create the registration object in our custom section,
and make sure our library can be loaded cleanly, regardless of
whether merging is actually enabled.
This requires a few tricks.
See the comments in that file for details.

[`jni_lib_merge.c`](https://github.com/fbsamples/android-native-library-merging-demo/blob/master/src/com/facebook/jnimerge/jni_lib_merge.c)
is our glue library,
which will automatically be included in every merged library.
It's responsible for defining the real `JNI_OnLoad`.
When the merged library is loaded,
it collects all of the function pointers
for the wrappers of the original `JNI_OnLoad` functions
and registers them with `Invoke_JNI_OnLoad`
so they can be called at the appropriate time.

Finally,
[`apps/BUCK`](https://github.com/fbsamples/android-native-library-merging-demo/blob/master/src/com/facebook/jnimerge/BUCK)
defines the merge map for each app.
In this case, we're merging all libraries into a single `libeverything`.
However, it's also possible to merge different subsets of libraries together:
for example, one library for everything that's related during app startup
and another for everything that's needed for camera effects.

Once these changes are made, we can run
`buck install //apps:animals`
and see that the resulting APK has only `libeverything.so`,
but all the functionality from the original libraries remains.

## Scaling

Having a mechanism for merging native libraries is great,
but we also need a policy for determining what to merge.
This requires some understanding of the structure of the app.
The
[`scripts/analyze-apk.sh`](https://github.com/fbsamples/android-native-library-merging-demo/blob/master/scripts/analyze-apk.sh)
script can help with that process.
When run on an APK,
it generates an image that shows all native libraries in the app,
draws edges between them to represent their dependencies,
and colors the ones with `JNI_OnLoad`
so you know which ones need `allow_jni_merging`.
Sometimes, a commonly used library will create too many edges to see clearly.
In these cases,
they can be filtered out by editing the `grep` command and rerunning.

Using this graph, we can make some decisions about which libraries to merge.
One good choice is to merge all libraries used during app startup.
Since they have to be loaded anyway, we might as well load them all together.
A cluster of libraries with similar names might be another good candidate.
Frequently, it makes sense to merge a library with all of its dependencies,
though that can be a mistake if the dependencies are often used on their own.
A rule of thumb is that you want to combine as many libraries as possible
while minimizing the amount of code that is loaded unnecessarily.

One minor issue that pops up when writing the merge map
is that you need to specify it as patterns of build target names.
We generate a file at
`buck-out/path/to/app#generate_native_lib_merge_map_generated_code/shared_object_targets.txt`,
which will show the build target that generated each native library.

## Wrapping up

Implementing native library merging took many steps,
but the end result is that
native library developers can
declare their libraries and dependencies as they please
without being aware of it.
Each app in our codebase can declare its own `native_library_merge_map`
to transparently merge libraries based on its own usage patterns.
This makes it easy for us to push back the native library limit
and let our linker do better inter-library optimizations.

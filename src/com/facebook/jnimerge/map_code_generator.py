#!/usr/bin/env python
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals
import sys
import collections
import re


def get_base(libname):
    m = re.search(r'lib([-\w]+).so', libname)
    if not m:
        raise Exception('Bad library name: ' + libname)
    return m.group(1)

def sanitize(libname):
    return re.sub(r'\W', '_', libname)

def main(argv):
    pre_merge = []
    merged_to_constituents = collections.defaultdict(list)

    with open(argv[1]) as handle:
        for line in handle:
            src, dst = [ get_base(w) for w in line.strip().split() ]
            pre_merge.append(src)
            merged_to_constituents[dst].append(src)

    with open(argv[2], 'w') as handle:
        handle.write('''\
package com.facebook.soloader;

class MergedSoMapping {
  static String mapLibName(String preMergedLibName) {
    switch (preMergedLibName) {
''')

        for merged, constituents in sorted(merged_to_constituents.items()):
            for constituent in constituents:
                handle.write('      case "%s":\n' % constituent)
            handle.write('        return "%s";\n' % merged)

        handle.write('''\
      default:
        return null;
    }
  }

  static void invokeJniOnload(String preMergedLibName) {
    int result = 0;
    switch (preMergedLibName) {
''')

        for pm in sorted(pre_merge):
            handle.write('      case "%s":\n' % pm)
            handle.write('        result = Invoke_JNI_OnLoad.lib%s_so();\n' % sanitize(pm))
            handle.write('        break;\n')

        handle.write('''\
      default:
        throw new IllegalArgumentException(
            "Unknown library: " + preMergedLibName);
    }

    if (result != 0) {
      throw new UnsatisfiedLinkError("Failed to invoke native library JNI_OnLoad");
    }
  }

  static class Invoke_JNI_OnLoad {
''')

        for pm in sorted(pre_merge):
            handle.write('    static native int lib%s_so();\n' % sanitize(pm))

        handle.write('''\
  }
}
''')

if __name__ == '__main__':
    sys.exit(main(sys.argv))

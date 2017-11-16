/*
 * Copyright 2018-present, Facebook, Inc.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <stddef.h>
#include <jni.h>

static jstring nativeGetName(JNIEnv* env, jclass cls) {
  return (*env)->NewStringUTF(env, "ice");
}

JNIEXPORT jint JNI_OnLoad(JavaVM* vm, void* reserved) {
  JNIEnv* env;
  if ((*vm)->GetEnv(vm, (void**)&env, JNI_VERSION_1_6)) {
    return JNI_ERR;
  }

  jclass iceClass = (*env)->FindClass(env, "com/facebook/example/habitat/Ice");
  if (iceClass == NULL) {
    return JNI_ERR;
  }
  JNINativeMethod methods[] = {
    {"getName", "()Ljava/lang/String;", nativeGetName},
  };
  size_t nMethods = sizeof(methods) / sizeof(methods[0]);
  jint result = (*env)->RegisterNatives(env, iceClass, methods, nMethods);
  if (result != 0) {
    return JNI_ERR;
  }

  return JNI_VERSION_1_6;
}

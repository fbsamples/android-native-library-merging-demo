#!/bin/bash
set -e

ARCH=armeabi-v7a

WORKDIR=`mktemp -d`
trap "rm -rf $WORKDIR" EXIT HUP INT TERM

APK=`realpath $1`

cd $WORKDIR
unzip -q $APK "lib/$ARCH/*"
cd lib/$ARCH

(
  set +e
  echo 'digraph G {'
  for OBJ in *.so ; do
    objdump -p $OBJ | awk 'BEGIN{obj="'$OBJ'"};/NEEDED/{print "\"" obj "\" -> \"" $2 "\";"}' | grep -f <(ls *.so | sed 's/^/> "/')
    objdump -T $OBJ | grep -q JNI_OnLoad && echo \"$OBJ\"' [fillcolor = pink, style = filled];'
  done
  echo '}'
) | sed 's/"lib/"/g;s/\.so"/"/g' | grep -v -e 'regexes-to-ignore' | dot -Tpng > library-graph.png

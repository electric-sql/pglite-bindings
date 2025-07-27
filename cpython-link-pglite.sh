#!/bin/bash
reset

CC=${CC:-gcc}
PYTHON=${PYTHON:-$(which python3)}


WASM2C=pglite
SDKROOT=/tmp/fs/tmp/sdk


if echo $CC|grep gcc
then
    COPTS="-O0 -g0"
    CCOPTS="-Wno-attributes"
else
    COPTS="-O0 -g0"
    CCOPTS="-fbracket-depth=4096 -Wno-unknown-attributes"
fi

PYVER=$($PYTHON -V|cut -d' ' -f2|cut -d. -f1-2)
PYVER=${PYVER}$(python3-config --abiflags)

PYINC="-D__PYDK__=1 -shared $(python3-config --includes)"
PYEXT=$(python3-config --extension-suffix)
PYLD="-lpython$PYVER $(python3-config --ldflags)"

PGL_BUILD_NATIVE=$(echo -n build-${PG_BRANCH}/pglite-native)
PGL_DIST_NATIVE=$(echo -n dist-${PG_BRANCH}/pglite-native)
echo "
========================================================================
WASM2C=$WASM2C
COPTS=$COPTS

PYVER=$PYVER
PYEXT=$PYEXT

PYINC=$PYINC
PYLD=$PYLD

PGL_BUILD_NATIVE=${PGL_BUILD_NATIVE}
PGL_DIST_NATIVE=${PGL_DIST_NATIVE}
TARGET: ${PGL_DIST_NATIVE}/${WASM2C}$PYEXT
========================================================================
"

if md5sum -c md5sum$(python3-config --extension-suffix).txt
then
    echo "C file has not changed, skipping build"
else
    COMPILE="$CC -fPIC -Os -g0 $PYINC $CCOPTS -I${SDKROOT}/src/w2c2 -I${SDKROOT}/src/w2c2/w2c2 -o ${PGL_DIST_NATIVE}/${WASM2C}$PYEXT ${PGL_BUILD_NATIVE}/tmp.c ${SDKROOT}/native/wasi/libw2c2wasi.a $PYLD -lc"
    echo $COMPILE
    if time $COMPILE
    then
        md5sum ${PGL_BUILD_NATIVE}/tmp.c > md5sum$(python3-config --extension-suffix).txt
    fi
fi


pushd ${PGL_DIST_NATIVE}
    echo "

______________________________________
Testing with $PYTHON
$(pwd)
$(cat md5sum$(python3-config --extension-suffix).txt)
______________________________________

"


    if [ -f ${WASM2C}$PYEXT ]
    then
        env -i $PYTHON <<END
import sys
sys.path.append('.')

import ${WASM2C}
print(f" {${WASM2C}.info()=} ")

print("======================================================")
${WASM2C}.Begin()
print("___ 183 _____")
#print('initdb=', ${WASM2C}.pg_initdb() )
print("___ 185 ____")
${WASM2C}.End()
print("======================================================")

print("bye")
END
    else
        echo ${WASM2C}$PYEXT not found
    fi
    pwd
    du -hs *
popd

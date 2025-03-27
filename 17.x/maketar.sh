#!/bin/bash

LOG=$(grep pglite initdb.log | cut -d\" -f2|sort|uniq|grep -v ^pglite/base|grep -v py$)
reset

pushd /tmp
    > packlist

    for maybefile in $LOG
    do
        if [ -f "/tmp/$maybefile" ]
        then
            echo "/tmp/$maybefile" >> packlist
        else
            [ -f "$maybefile" ] && echo "$maybefile" >> packlist
        fi
    done
    pushd /
        tar -cvJ --files-from=/tmp/packlist > /tmp/pglite-prefix.tar.xz
        #gzip -9 /tmp/pglite-prefix.tar
        #lzma -9 /tmp/pglite-prefix.tar
    popd
popd

mv /tmp/pglite-prefix.tar.xz ./
du -hs pglite-prefix.*



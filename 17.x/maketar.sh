#!/bin/bash

# initdb.log is the strace got from running from /tmp/pglite real fs with no initial db

LOG=$(grep pglite initdb.log | cut -d\" -f2|sort|uniq|grep -v ^pglite/base|grep -v \.py$|grep -v \.so$)
reset

pushd /tmp
    find /tmp/pglite/share/postgresql/* -type f |grep UTC$> packlist
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
        XZ_OPT=-9 tar -cv --lzma --files-from=/tmp/packlist > /tmp/pglite-prefix.tar.xz
    popd
popd

mv /tmp/pglite-prefix.tar.xz ./
du -hs pglite-prefix.*



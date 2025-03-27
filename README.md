# libpglite
- libpglite is a thin load/wrapper around postgresql backend, initdb, and some transport facilities inspired from frontends.
- initdb part is fully automated to create a default database "template1" with user "postgres" with md5 password "password" in "/tmp/pglite/base" folder ( real or not ).
- libpglite part only takes queries in input, and output results. All encoded in UTF-8.

    - possible inputs are:

        - REPL style input : sql command ended by a ";" and a newline.
        - Wire protocol queries
```
mode is controlled by pglite.use_wire(0/1)
-> pglite.use_wire(1) means use wire protocol,
-> pglite.use_wire(0) means repl style.

NB: wire mode requires you to know the size of encoded query ( set with pglite.interactive_write(int) ).
while repl style uses C style \0 termination of query buffer, or EOF in case of file transport.
```


## memory/file transport:

#### Queries:

- from memory at (wasm) address 0x1
- from a file named  "/tmp/pglite/base/.s.PGSQL.5432.lock.in" : the file is renamed to "/tmp/pglite/base/.s.PGSQL.5432.in" when ready


#### Replies:

- when using REPL style input, reply is printed on STDOUT as utf-8.
- when using wire replies go by default on same transport as input :
    * file input always gets on file named "/tmp/pglite/base/.s.PGSQL.5432.out"
    * memory input get memory output, except if results is overflowing : then it will go to file output. ( N/I )

```
    size of reply when using wasm memory is given by  pglite.interactive_read() as an integer.
    offset of reply is 2+query size as in this layout:

    [ 1, query, gap of 1,  result ]
```




## libpglite API (WIP!):

in any case default C calling conventions apply and filesystems follow POSIX conventions. C.UTF-8 is the default locale and cannot be changed.


for generic setup,  setenv/getenv is used
Keeping keys close to actual postgres env control, or maybe prefixed PGL_ when it only concerns the pglite bridge.

___
in order of call :
___

- pg_initdb() → int
    - call initdb and returns status from bitmask
```
IDB_OK 0b11111110 → db has resumed normally
IDB_FAILED 0b0001  → creation or resume of db failed
IDB_CALLED 0b0010  → initdb was called and db created
IDB_HASDB 0b0100  → the db has been found
IDB_HASUSER 0b1000  → the user exists
```
- pg_conf(key, value)
    - value to set in PREFIX/postgresql.conf
- pgl_backend()
    - (re)init postgres backend after initdb and config edition ( in postgres it would be the equivalent of fork(). it can change username but is tied to it till fred and restart).

___
Transport related , need probably better names. ( interactive_one is CPython , CMA comes  from linux kernel ). A PRIORI the transport is only tied to a portion of shared memory, a memory context ( which is specific to above backend)  and a 8KB buffer that WILL overflow so we need to dump to a file when it happens.
___


- use_wire(0/1)
    - state if data in buffer will use wire protocol
- interactive_write(len)
    - length of input data when using cma buffer, force the use of cma for input.
- use_cma(0/1)
    - state if cma buffer is used for reply else default to same as input. cannot yet redirect repl output.
- interactive_one(void)
    - process input stream ( auto selected from socketfiles/cma)
- interactive_read() → int
    - size of reply from pgcore.

```
possible negative return:
    overflow happened on CMA reply
    whole content is to be found in a memory file instead
    possible to index memory files names with abs(return value)
```

___
error handling ( currently N/I outside emscripten build )
___

clear_error(void): clear previous exception.











# pglite-bindings
(WIP) various language support for libpglite native

Currently testing working with wasmtime offical embedding:

- python unix socket gateway to pglite ( tested against pg_dump/psql )

    pglite: `python3 17.x/wasi-python/pglite-wasi-gateway.py`

    a client: `psql "host=/tmp user=postgres sslmode=disable password=postgres require_auth=md5 dbname=template1"`





Also some Community experiments :

    WIP Go REPL:
        https://github.com/sgosiaco/pglite-go/

    WIP kotlin/graalvm:
        https://github.com/emrul/pglite-graalvm



issues tracking:

    generic:
    https://github.com/electric-sql/pglite/issues/89


    python:
    https://github.com/electric-sql/pglite/issues/226


    react:
    https://github.com/electric-sql/pglite/issues/87







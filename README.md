# libpglite
- libpglite is a thin load/wrapper around postgresql backend, initdb, and some transport facilities inspired from frontends.
- initdb part is fully automated to create a default database "template1" with user "postgres" with md5 password "password" in "/tmp/pglite/base" folder ( real or not ).
- libpglite part only take queries in input, and output results. All encoded in UTF-8.

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
    offset of reply is 3+query size as in this layout:

    [ 1, query, gap of 2,  result ]
```












# pglite-bindings
(WIP) various language support for libpglite native

Currently working with wasmtime offical embedding:

- python unix socket gateway to pglite ( tested against pg_dump/psql )

    pglite: `python3 17.x/wasi-python/pglite-wasi-gateway.py`

    a client: `psql "host=/tmp user=postgres sslmode=disable password=postgres require_auth=md5 dbname=template1"`





Also some Community experiments :

    a Go REPL:
        https://github.com/sgosiaco/pglite-go/

    WIP kotlin/graalvm:
        https://github.com/emrul/pglite-graalvm



tracking:

    generic:
    https://github.com/electric-sql/pglite/issues/89


    python:
    https://github.com/electric-sql/pglite/issues/226


    react:
    https://github.com/electric-sql/pglite/issues/87






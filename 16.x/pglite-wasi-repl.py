#!/usr/bin/env python3

import socket


if 1:

    class mock_socket(socket.socket):


        def __init__(self, *argv, **kw):
            super().__init__(*argv, **kw)
            self.peek = 0
            self.out = []


        def connect(self, *argv, **kw):
            print("mock connect", argv, kw)

        def send(self, data, flags=""):
            print("mock send", len(data))
            self.out.append(data)
            return len(data)

        def sendall(self, data, flags=""):
            global pglite
            nb = 0
            if data:
                print("mock sendall", len(data))
                self.out.append(data)

            if self.out:
                print(f"    sendall->flushing {nb}")
                sql_bytes_cstring = b"".join( self.out )
                nb = len(sql_bytes_cstring)
                pglite.use_wire(1)
                pglite.interactive_write(nb)
                print(sql_bytes_cstring)
                pglite.Memory.mpoke(1, sql_bytes_cstring)
                pglite.interactive_one()
                self.peek = pglite.interactive_read()
                print(f"    sendall->flushed {nb}, reply {self.peek}")
                self.out.clear()
            return nb

        def recv(self, buffersize, flags=""):
            self.sendall(None)
            print("mock recv", buffersize, flags)
            return b"\0" * self.peek

        def recv_into(self, buffer, nbytes=0, flags=""):
            if nbytes:
                if nbytes<self.peek:
                    nbytes = self.peek
            print("mock recv_into", buffer, nbytes, flags)
            return 0


        def makefile(self, flags):
            print("mock makefile",flags)
            return socket.socket.makefile(self, flags)


    socket.socket = mock_socket

    import pg8000.core
    def mock_flush(*argv):
        print("mock_flush")

    pg8000.core._flush = mock_flush


import os
import sys
import time
import asyncio
import traceback

from os.path import isfile as is_file


try:
    import wasmtime
except:
    os.system(f"{sys.executable} -m pip install --user wasmtime")
    __import__("importlib").invalidate_caches()
    import wasmtime


# asyncpg psycopg
# https://pypi.org/project/pgsql/
# https://github.com/tlocke/pg8000


try:
    import pg8000.native as pg
except:
    os.system(f"{sys.executable} -m pip install --user pg8000")
    __import__("importlib").invalidate_caches()
    import pg8000.native as pg


MOUNT = "tmp"
if is_file("tmp/pglite/base/PG_VERSION"):
    print(" ---------- local db -------------")

elif is_file("/tmp/pglite/base/PG_VERSION"):
    print(" ---------- devel db -------------")
    MOUNT = "/tmp"
else:
    print(" ---------- demo db -------------")
    with __import__("tarfile").open("pglite-wasi.tar.gz") as archive:
        archive.extractall(".")


async def get_reader(stream=sys.stdin) -> asyncio.StreamReader:
    stream_reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(stream_reader)
    loop = asyncio.get_running_loop()
    await loop.connect_read_pipe(lambda: protocol, stream)
    return stream_reader


async def ainput(prompt=""):
    try:
        async_fd = await get_reader(sys.stdin)
    except ValueError:
        return b"q"
    print(prompt, end="", flush=True)
    return await async_fd.readline()


class wasm_import:
    import os

    os.environ["WASMTIME_BACKTRACE_DETAILS"] = "1"

    class __module:

        def __init__(self, vm, wasmfile):
            self.store = vm.store
            self.module = vm.Module.from_file(vm.linker.engine, wasmfile)
            self.instance = vm.linker.instantiate(self.store, self.module)
            self.mem = self.instance.exports(self.store)["memory"]
            self.get("_start")()

        def get(self, export):

            call = self.instance.exports(self.store)[export]
            store = self.store

            def bound(*argv, **env):
                return call(store, *argv, **env)

            return bound

        def __all__(self):
            return list(wasm_mod.instance.exports(wasm_mod.store).keys())

    #  #, Instance, Trap, MemoryType, Memory, Limits, WasmtimeError

    from wasmtime import WasiConfig, Linker, Engine, Store, Module

    config = WasiConfig()
    config.argv = ["--single", "postgres"]
    # config.inherit_argv()

    env = [
        ["ENVIRONMENT", "wasi-embed"],
    ]

    # config.inherit_env()

    config.inherit_stdout()
    config.inherit_stderr()

    config.preopen_dir(MOUNT, "/tmp")
    if not os.path.isdir("dev"):
        os.mkdir("dev")
    with open("dev/urandom", "wb") as rng_out:
        rng_out.write(os.urandom(128))
    config.preopen_dir("dev", "/dev")

    linker = Linker(Engine())
    # linker.allow_shadowing = True
    linker.define_wasi()

    store = Store(linker.engine)

    def __init__(self, alias, wasmfile, **env):
        for k, v in env.items():
            self.env.append([k, v])
        self.config.env = self.env
        self.store.set_wasi(self.config)

        import sys

        py_mod = type(sys)(alias)
        wasm_mod = self.__module(self, wasmfile)

        class Memory:
            def __init__(self, mem, mod):
                self.mem = mem
                self.mod = wasm_mod

            def mpoke(self, addr, b):
                return self.mod.mem.write(self.mod.store, b, addr)

            def mpeek(self, addr, stop: None):
                return self.mod.mem.read(self.mod.store, addr, stop)

            def __getattr__(self, attr):
                if attr == "size":
                    return self.mod.mem.size(self.mod.store)
                if attr == "data_len":
                    return self.mod.mem.data_len(self.mod.store)
                return object.__getattr__(self, attr)

        for k, v in wasm_mod.instance.exports(wasm_mod.store).items():
            if k == "memory":
                setattr(py_mod, "Memory", Memory(v, wasm_mod))
                continue
            if k == "_start":
                continue
            setattr(py_mod, k, wasm_mod.get(k))

        sys.modules[alias] = py_mod


def SI(n):
    intn = int(n)
    n = float(n)
    if intn < 1024:
        return "%3.0f B" % n

    if intn // 1024 < 999:
        return "%3.2f kiB" % (n / 1024)

    mb = 1048576
    if intn // mb < 999:
        return "%3.2f MiB" % (n / mb)

    gb = 1073741824
    if intn // gb < 999:
        return "%3.2f GiB" % (n / gb)

    return n


if is_file("/tmp/pglite/bin/postgres.wasi"):
    print("  ========== devel version =============")
    wasm_import("pglite", "/tmp/pglite/bin/postgres.wasi", **{"REPL": "N", "PGUSER": "postgres", "PGDATABASE": "postgres"})
else:
    print("  -------- demo version ----------")
    wasm_import("pglite", "tmp/pglite/bin/postgres.wasi", **{"REPL": "N", "PGUSER": "postgres", "PGDATABASE": "postgres"})

import pglite


rv = pglite.pg_initdb()

print(
    f"""

initdb returned : {bin(rv)}

{SI(pglite.Memory.size)=}

{SI(pglite.Memory.data_len)=} <= with included 32 MiB shared memory

{pglite=}
"""
)
for k in dir(pglite):
    print("\t", k)


TESTS = """

SHOW client_encoding;

CREATE OR REPLACE FUNCTION test_func() RETURNS TEXT AS $$ BEGIN RETURN 'test'; END; $$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION addition (entier1 integer, entier2 integer)
RETURNS integer
LANGUAGE plpgsql
IMMUTABLE
AS '
DECLARE
  resultat integer;
BEGIN
  resultat := entier1 + entier2;
  RETURN resultat;
END ' ;

SELECT test_func();

SELECT now(), current_database(), session_user, current_user;

SELECT addition(40,2);

"""

DONE = 0


def poke(string):
    sql_bytes_cstring = string.encode("utf-8") + b"\0"  # <- do not forget this one, wasmtime won't add anything!
    pglite.Memory.mpoke(1, sql_bytes_cstring)
    pglite.interactive_write(len(sql_bytes_cstring))


async def tests():
    global DONE
    for line in TESTS.split(";\n\n"):
        await asyncio.sleep(0.5)

        if line.strip():
            line = line.strip() + ";"
            print(f"REPL: {line}")
            poke(line)

    await asyncio.sleep(0.5)
    DONE = 1






if 1:

    DBH = {"q": {}}

    class DB:
        name: str = "name"
        user: str = "postgres"
        password: str = "md53175bce1d3201d16594cebf9d7eb3f9d"

        if 0:
            addr: str = "82.66.105.11"  # 127.0.0.1"
            host: str = "pmp-p.ddns.net/wss/5432"  # "localhost"
            port: int = 443
        else:
            addr: str = "127.0.0.1"
            host: str = "localhost"
            port: int = 5432

        conn: str = "url"
        cursor: object = None

    def describe(dbname):
        global DBH
        dbnl = dbname.lower()
        db = DBH.get(dbnl, None)

        if db is None:
            db = DB()
            db.name = dbnl
            db.conn = f"host='{db.host}' hostaddr='{db.addr}' dbname='{db.name}' port={db.port} user='{db.user}' password='{db.password}' sslmode='disable'"
            try:
                db.conn = psycopg.connect(db.conn)
                db.cursor = db.conn.cursor()
            except Exception as e:
                print("FAIL", db.conn, e)
                raise

            DBH[dbnl] = db
            DBH["current"] = dbnl

        else:
            print("reusing", db, "for", dbnl)
        return db

if 1:
    async def main():
        global DONE
        # pglite.interactive_one();

        SCK="/tmp/.s.PGSQL.5432"
        if os.path.exists(SCK):
            con = pg.Connection(DB.user, host="127.0.0.1", port= 5432, database="template1", ssl_context=None, application_name="psql", unix_sock=SCK, password="password", tcp_keepalive=False, timeout=1)
        else:
            con = pg.Connection(user="login", database="postgres", host="127.0.0.1", port=5432, ssl_context=None, application_name="test", password="password")

        for row in con.run("SELECT now()"):
            print(row)

#        cur = con.cursor()
#        cur.execute(
#        print( cur.fetchone()[0] )

        await asyncio.sleep(0.016)

        con.close()
        # describe("postgres")
        print("bye")

else:

    async def main():
        global DONE

        pglite.use_socketfile()

        asyncio.get_running_loop().create_task(tests())
        i = 0
        while True:
            pglite.use_wire(0)
            pglite.interactive_one()
            reply = pglite.interactive_read()
            if reply:
                print("CMA reply length :", reply)
                pglite.interactive_write(0)
            await asyncio.sleep(0.016)
            if DONE:
                sql = await ainput("sql> ")
                sql = sql.decode().strip()
                if sql == "q":
                    break
                print(f"user input: {sql}")
                poke(sql)

        print("bye")


asyncio.run(main())

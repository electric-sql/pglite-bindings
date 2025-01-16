#!/usr/bin/env python3
import os
import sys
import time
import asyncio
import traceback

import select
import socket


USE_CMA = 'nocma' not in sys.argv
CMA_QUERY = 0
USER_SQL = ""

SYS_QUIT = USER_QUIT = False
FD = -1

# Set the path for the Unix socket
socket_path = "/tmp/.s.PGSQL.5432"

# set base path for I/O ( wasi fs )
io_path = "./tmp/pglite/base/.s.PGSQL.5432"

SINPUT = f"{io_path}.in"
SLOCK = f"{io_path}.lock.in"

CINPUT = f"{io_path}.out"
CLOCK = f"{io_path}.lock.out"

CLOCK_in_progress = False


def slock():
    global SLOCK
    with open(SLOCK, "wb") as file:
        pass


def sunlock():
    global SLOCK
    os.unlink(SLOCK)


def print_exception(e, out=sys.stderr, **kw):
    kw["file"] = out
    traceback.print_exc(**kw)


sys.print_exception = print_exception


try:
    import wasmtime
except:
    import os

    os.system(f"{sys.executable} -m pip install --user wasmtime")
    __import__("importlib").invalidate_caches()

MOUNT = "tmp"
if os.path.isfile("tmp/pglite/base/PG_VERSION"):
    print(" ---------- local db -------------")

elif os.path.isfile("/tmp/pglite/base/PG_VERSION"):
    print(" ---------- devel db -------------")
    MOUNT = "/tmp"
else:
    print(" ---------- demo db -------------")
    with __import__("tarfile").open("pglite-wasi.tar.gz") as archive:
        archive.extractall(".")


class wasm_import:
    import os

    # os.environ["WASMTIME_BACKTRACE_DETAILS"] = "1"

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



def SI(n):
    intn = int(n)
    n = float(n)
    if intn < 1024:
        return "%3.0f B" % n

    if (intn // 1024) < 999:
        return "%3.2f kiB" % (n / 1024)

    if (intn // 1048576) < 999:
        return "%3.2f MiB" % (n / 1048576)

    if (intn // 1073741824) < 999:
        return "%3.2f GiB" % (n / 1073741824)

    return n


if os.path.isfile("/tmp/pglite/bin/postgres.wasi"):
    print("  ========== devel version =============")
    wasm_import("pglite", "/tmp/pglite/bin/postgres.wasi", **{"REPL": "N", "PGUSER": "postgres", "PGDATABASE": "postgres"})
else:
    print("  -------- demo version ----------")
    wasm_import("pglite", "tmp/pglite/bin/postgres.wasi", **{"REPL": "N", "PGUSER": "postgres", "PGDATABASE": "postgres"})


import pglite


rv = pglite.pg_initdb()


def dbg(code, data):
    fit = int(100 / 2)
    if len(data) > (fit * 2):
        print(code, len(data), data[:fit], "...", data[-fit:])
    else:
        print(code, str(len(data)).zfill(2), data)


class Client:
    def __init__(self, clientSocket, targetHost, targetPort):
        self.__clientSocket = clientSocket

    async def run(self):
        global pglite, CMA_QUERY, USER_SQL

        # initial clean up
        for f in [SINPUT, CINPUT]:
            try:
                os.remove(f)
                print(f"removed {f}")
            except:
                pass

        print("Client Thread started")

        if not USE_CMA:

            def pump():
                global CLOCK_in_progress
                cdata = None
                if not CLOCK_in_progress:
                    if os.path.isfile(CLOCK):
                        print(f"{CLOCK} : server is reply in progress ...")
                        CLOCK_in_progress = True

                if os.path.isfile(CINPUT):
                    with open(CINPUT, "rb") as file:
                        cdata = file.read()
                    os.unlink(CINPUT)
                    dbg(f"\n232: {CINPUT} : pg->cli", cdata)
                    CLOCK_in_progress = False
                return cdata

        else:
            def pump():
                global CMA_QUERY
                reply = pglite.interactive_read()
                if reply:
                    cdata = bytes( pglite.Memory.mpeek(0, CMA_QUERY+2 +  reply)[CMA_QUERY+2:] )
                    print(f"CMA reply length {reply} at {CMA_QUERY+2}:", cdata)
                    pglite.interactive_write(0)
                    CMA_QUERY = 0
                else:
                    cdata = None
                return cdata


        try:
            self.__clientSocket.setblocking(0)
        except:
            print(self.__clientSocket, "setblocking failed")

        clientData = b""
        targetHostData = b""
        terminate = False

        while not (USER_QUIT or SYS_QUIT):

            if USER_SQL:
                send_line(USER_SQL)
                USER_SQL =""
                pglite.interactive_one()

            inputs = [self.__clientSocket]
            outputs = []

            if len(clientData) > 0:
                outputs.append(self.__clientSocket)

            try:
                inputsReady, outputsReady, errorsReady = select.select(inputs, outputs, [], 0.016)
            except Exception as e:
                sys.print_exception(e)
                break

            data = None
            for inp in inputsReady:
                if inp == self.__clientSocket:
                    data = None
                    try:
                        data = self.__clientSocket.recv(4096)
                    except Exception as e:
                        print("102", e)

                    if data != None:
                        if len(data) > 0:
                            targetHostData += data
                        else:
                            terminate = True
            if targetHostData:
                outputsReady.append("pglite")

            data = pump()
            if data and len(data) > 0:
                clientData += data

            bytesWritten = 0

            for out in outputsReady:
                if out == self.__clientSocket and (len(clientData) > 0):
                    bytesWritten = self.__clientSocket.send(clientData)
                    if bytesWritten > 0:
                        clientData = clientData[bytesWritten:]

                elif out == "pglite" and (len(targetHostData) > 0):
                    bytesWritten = len(targetHostData)
                    print("unixsocket -> pglite", bytesWritten, targetHostData)
                    if bytesWritten > 0:
                        if not USE_CMA:
                            with open(SLOCK, "wb") as file:
                                file.write(targetHostData[:bytesWritten])

                            # atomic
                            os.rename(SLOCK, SINPUT)

                        else:
                            CMA_QUERY = bytesWritten
                            pglite.interactive_write(CMA_QUERY)
                            pglite.Memory.mpoke(1, targetHostData[:bytesWritten])

                        targetHostData = targetHostData[bytesWritten:]

            if bytesWritten > 0:
                pglite.use_wire(1)
                try:
                    pglite.interactive_one()
                except Exception as e:
                    sys.print_exception(e)
                    pglite.clear_error()
                    pglite.use_wire(1)
                    pglite.interactive_write(0)
                    pglite.interactive_one()


            await asyncio.sleep(0.016)


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


def send_line(line):
    pglite.use_wire(0)
    line = line.rstrip("\r\n; ") + ";"
    print(f"REPL: {line}")
    sql_bytes_cstring = line.encode("utf-8") + b"\0"  # <- do not forget this one, wasmtime won't add anything!
    pglite.Memory.mpoke(1, sql_bytes_cstring)


async def tests():
    global DONE
    for line in TESTS.split(";\n\n"):
        await asyncio.sleep(0.5)
        if line.strip():
            send_line(line)
    await asyncio.sleep(0.5)
    DONE = 1

async def repl():
    global USER_SQL, USER_QUIT, SYS_QUIT
    while not SYS_QUIT:
        sql = await ainput("sql> ")
        sql = sql.decode().strip()
        if sql == "q":
            USER_QUIT = True
            return
        USER_SQL = sql


async def main():
    global DONE

    if not USE_CMA:
        pglite.use_socketfile()

    if "inet" not in sys.argv:
        # remove the socket file if it already exists
        try:
            os.unlink(socket_path)
        except OSError:
            if os.path.exists(socket_path):
                raise

        # Create the Unix socket server
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)

        # Bind the socket to the path
        server.bind(socket_path)
    else:
        # create a tcp server instead
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(("0.0.0.0", 5432))

    # Listen for incoming connections
    server.listen(1)

    asyncio.get_running_loop().create_task(tests())

    # wait above test finished before accept connections
    while True:
        if DONE:
            break
        pglite.interactive_one()
        await asyncio.sleep(0.016)

    asyncio.get_running_loop().create_task(repl())

    while not USER_QUIT:
        print("Server is listening for incoming connections...")
        connection, client_address = server.accept()


        FD = connection.fileno()
        await Client(connection, "127.0.0.1", 5432).run()
        print("Client task terminating")

        connection.close()

    server.close()

asyncio.run(main())

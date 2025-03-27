import sys
import os
import asyncio
import tarfile
import importlib

from os.path import isfile as is_file

# from https://pypi.org/project/wasmtime/
try:
    import wasmtime
except:
    os.system(f"{sys.executable} -m pip install --user wasmtime")
    importlib.invalidate_caches()
    import wasmtime



MOUNT = "tmp"
if is_file("tmp/pglite/base/PG_VERSION"):
    print(" ---------- local db -------------")

elif is_file("/tmp/pglite/base/PG_VERSION"):
    print(" ---------- devel db -------------")
    MOUNT = "/tmp"
else:
    print(" ---------- demo db -------------")
    try:
        with tarfile.open("17.x/pglite-prefix.tar.xz") as archive:
            archive.extractall(".")
        MOUNT = "tmp"
    except FileNotFoundError:
        print("demo pkg not found: will attempt to use initdb to create initial db from /tmp/pglite prefix")
        MOUNT = "/tmp"


# set base path for I/O ( wasi fs )
io_path = "/tmp/pglite/base/.s.PGSQL.5432"
if not MOUNT.startswith('/'):
    io_path = '.' + io_path



class wasm_import:
    import os

    current = None

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
        wasm_import.current = py_mod

def poke(string):
    if isinstance(string, str):
        sql_bytes_cstring = string.encode("utf-8") + b"\0"  # <- do not forget this one, wasmtime won't add anything!
    else:
        sql_bytes_cstring = string
    nb = len(sql_bytes_cstring)
    print(f"SENDING[{nb}]:", sql_bytes_cstring)
    wasm_import.current.Memory.mpoke(1, sql_bytes_cstring)
    wasm_import.current.interactive_write(nb)
    return nb



# tools

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

    if intn // 1024 < 999:
        return "%3.2f kiB" % (n / 1024)

    mb = 1048576
    if intn // mb < 999:
        return "%3.2f MiB" % (n / mb)

    gb = 1073741824
    if intn // gb < 999:
        return "%3.2f GiB" % (n / gb)

    return n

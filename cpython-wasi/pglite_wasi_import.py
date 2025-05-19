import sys
import os
import asyncio
import tarfile
import importlib


# sync op
from os.path import isfile as is_file

def pip_install(pkg, fqn=''):
    try:
        __import__(pkg)
    except:
        os.system(f'"{sys.executable}" -m pip install --user {fqn or pkg}')
        __import__("importlib").invalidate_caches()
    return __import__(pkg)

for req in ('wasmtime','aiohttp'):
    pip_install(req)

import wasmtime

# defaults
MOUNT = "tmp"
IO_PATH = "/tmp/pglite/base/.s.PGSQL.5432"

sync_importer = None

async def main():
    global MOUNT, IO_PATH

    if is_file("tmp/pglite/base/PG_VERSION"):
        print(" ---------- local db -------------")

    elif is_file("/tmp/pglite/base/PG_VERSION"):
        print(" ---------- devel db -------------")
        MOUNT = "/tmp"
    else:
        print(" ---------- demo db -------------")
        async def download_file(url, output_path=None):
            import aiohttp
            if output_path is None:
                output_path = url.rsplit('/',1)[-1]

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        print(f"Failed to fetch {url}: HTTP {response.status}")
                        return

                    # Get the total file size from headers
                    total_size = int(response.headers.get('Content-Length', 0))
                    downloaded_size = 0
                    chunk_size = 1024  # 1KB

                    # Open the output file for writing
                    with open(output_path, 'wb') as file:
                        print(f"Downloading {url}...\n")

                        while True:
                            chunk = await response.content.read(chunk_size)
                            if not chunk:
                                break

                            file.write(chunk)
                            downloaded_size += len(chunk)

                            # Update the progress bar
                            percentage = int(downloaded_size * 100 / total_size) if total_size else 0
                            progress_bar = f"[{'=' * (percentage // 2)}{' ' * (50 - percentage // 2)}]"
                            sys.stdout.write(f"\r{progress_bar} {percentage}%")
                            sys.stdout.flush()

                    print(f"\nDownloading of {url} complete.")
                    return True
        if not await download_file("http://pmp-p.ddns.net/pglite-web/pglite-wasi.tar.xz"):
            print("dev build not found, falling back to CI build")
            await download_file("https://electric-sql.github.io/pglite-build/pglite-wasi.tar.xz")

        try:
            with tarfile.open("pglite-wasi.tar.xz") as archive:
                archive.extractall(".")
            MOUNT = "tmp"
        except FileNotFoundError:
            print("demo pkg not found: will attempt to use initdb to create initial db from /tmp/pglite prefix")
            MOUNT = "/tmp"

    await asyncio.sleep(0)


    # set base path for I/O ( wasi fs )
    if not MOUNT.startswith('/'):
        IO_PATH = '.' + IO_PATH

    print(f"""

{MOUNT=}
{IO_PATH=}

""")

    class wasi_import:
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
            wasi_import.current = py_mod

    return wasi_import

def poke(string):
    if isinstance(string, str):
        sql_bytes_cstring = string.encode("utf-8") + b"\0"  # <- do not forget this one, wasmtime won't add anything!
    else:
        sql_bytes_cstring = string
    nb = len(sql_bytes_cstring)
    print(f"SENDING[{nb}]:", sql_bytes_cstring)
    wasi_import.current.Memory.mpoke(1, sql_bytes_cstring)
    wasi_import.current.interactive_write(nb)
    return nb



# tools

def hexc(byte_data, way="<->", lines=-1):
    result = []
    lower = upper = offset = 0

    total = int( (len(byte_data) / 16) )
    if lines>0:
        if total > lines+1:
            lower = int( (16*lines)/2)
            upper = int(16*total - lower)
        else:
            lines = -1
    print(f"{way} : {len(byte_data)} bytes, {len(byte_data)/16}/{total} lines, limit={lower}] [{upper}")
    ignore = False
    for i in range(0, len(byte_data), 16):
        chunk = byte_data[i:i+16]
        hex_values = " ".join(f"{int(byte):02x}" for byte in chunk)
        ascii_values = "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in chunk)
        if lines > 0:
            if i>upper:
                ignore = False
            elif i>lower:
                if not ignore:
                    ignore = True
                    hex_values= f'... {upper:08x}'
                    ascii_values = f'<skipping {lower*16} to {upper*16}>'
                else:
                    offset += 16
                    continue

        result.append(f"{offset:08x} {hex_values:<47}  {ascii_values}")
        offset += 16
    return "\n".join(result)

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


def get_io_base_path():
    global sync_importer
    if sync_importer is None:
        raise Exception("No wasi module in use")
    return IO_PATH


async def wasm_import(alias, wasmfile, **options):
    global sync_importer
    if sync_importer is None:
        sync_importer = await main()
    print(f"importing {alias} from {wasmfile}")
    return sync_importer(alias, wasmfile, **options)



if __name__ == "__main__":
    print("begin")
    asyncio.run(main())
    print("end")




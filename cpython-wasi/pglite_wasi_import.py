import sys
import os
import asyncio
import tarfile
import importlib


# sync op
from os.path import isfile as is_file


# defaults
MOUNT = "tmp"
IO_PATH = "/tmp/pglite/base/.s.PGSQL.5432"
sync_wasi_importer = None


async def main():
    global MOUNT, IO_PATH

    if is_file("tmp/pglite/base/PG_VERSION"):
        print(" ---------- local db -------------")

    elif is_file("/tmp/pglite/base/PG_VERSION"):
        print(" ---------- devel db -------------")
        MOUNT = "/tmp"
    else:
        print(" ---------- unpacking demo db -------------")
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

    return __import__('pywasi').set_fs(MOUNT)




#
async def wasm_import(alias, wasmfile, **options):
    global sync_wasi_importer
    # any extra async io like getting the wasm to be done here.

    # return a wasm module mapped to python
    if sync_wasi_importer is None:
        sync_wasi_importer = await main()
    return sync_wasi_importer(alias, wasmfile, **options)


def pg_dump(bin, imports, argv):
    sync_wasi_importer('pg_dump', bin, imports = imports, argv=argv)



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
        return "%3.2f KiB" % (n / 1024)

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
    return IO_PATH



if __name__ == "__main__":
    print("begin")
    asyncio.run(main())
    print("end")




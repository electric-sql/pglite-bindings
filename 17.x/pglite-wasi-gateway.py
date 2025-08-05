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


PKT_NUM = 0


# Set the path for the Unix socket
socket_path = "/tmp/.s.PGSQL.5432"

from pglite_wasi_import import wasm_import, pg_dump, is_file, poke, ainput, get_io_base_path, hexc, SI

options = {
    "REPL": "N",
    "PGUSER": "postgres",
    "PGDATABASE": "template1",
    "PREFIX": "/tmp/pglite",
}

if is_file("/tmp/fs/tmp/pglite/bin/pglite.wasi"):
    print("  ========== devel version =============")
    wasi_bin = "/tmp/fs/tmp/pglite/bin/pglite.wasi"
    pg_dump_bin  = "/tmp/fs/tmp/pglite/bin/pg_dump.wasi"
    PROMPT = "devel>"

elif is_file("/srv/www/html/pglite-web/pglite.wasi"):
    print("  ========== latest version =============")
    wasi_bin = "/srv/www/html/pglite-web/pglite.wasi"
    pg_dump_bin  = "/srv/www/html/pglite-web/bin/pg_dump.wasm"
    PROMPT = "latest>"
else:
    print("  -------- demo version ----------")
    wasi_bin = "tmp/pglite/bin/pglite.wasi"
    pg_dump_bin  = "tmp/pglite/bin/pgdump.wasi"
    PROMPT = "demo>"



await wasm_import("pglite", wasi_bin, imports={}, argv=("--single", "postgres",), **options)

io_path = get_io_base_path()


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


import pglite

rv = pglite.pgl_initdb()

# start backend after initdb and configuration tuning
pglite.pgl_backend()

print(
    f"""

{wasi_bin = }
{pg_dump_bin = }

File Transport :

{SLOCK=}
{SINPUT=}

{CLOCK=}
{CINPUT=}

CMA Transport :
addr={pglite.get_buffer_addr(0)}
size={pglite.get_buffer_size(0)}

initdb returned : {bin(rv)}

{SI(pglite.Memory.size)=}

{SI(pglite.Memory.data_len)=} <= with included {SI(pglite.get_buffer_size(0))} shared memory

-------------- API (wip) --------------
{pglite=}
"""
)

for k in dir(pglite):
    print("\t", k)

print("""
---------------------------------------
""")



def dbg(code, data):
    fit = int(100 / 2)
    if len(data) > (fit * 2):
        print(code, len(data), data[:fit], "...", data[-fit:])
    else:
        print(code, str(len(data)).zfill(2), data)


class Client:
    cids = 0
    connected = 0

    def __init__(self, clientSocket, targetHost, targetPort):
        self.__class__.cids += 1
        self.cid = self.cids
        self.__clientSocket = clientSocket
        print(f'\t[[[[  New client [#{self.cid}] connection started', clientSocket, targetHost, targetPort, ' ]]]]')

    async def run(self):
        global pglite, CMA_QUERY, USER_SQL, PKT_NUM

        # initial clean up
        for f in [SINPUT, CINPUT]:
            try:
                os.remove(f)
                print(f"removed {f}")
            except:
                pass

        def pump_sf():
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
                dbg(f"\n130: {CINPUT} : pg->cli", cdata or '')
                CLOCK_in_progress = False
            return cdata

        def pump_cma():
            global CMA_QUERY
            reply = pglite.interactive_read()
            if reply:
                cdata = bytes( pglite.Memory.mpeek(2+CMA_QUERY,CMA_QUERY+2+reply) )
                print(f"pglite -> socket [#{self.cid}], reply length {reply} at {CMA_QUERY+3}:")
                pglite.interactive_write(0)
                CMA_QUERY = 0
            else:
                cdata = None
            return cdata

        def pump():
            if pglite.get_channel()<0:
                return pump_sf()
            return pump_cma()



        try:
            self.__clientSocket.setblocking(0)
        except:
            print(self.__clientSocket, "setblocking failed")

        clientData = b""
        targetHostData = b""
        terminate = False

        Client.connected += 1

        # reset the prompt line
        print("\r\n-> new client connected")
        print(f"[{Client.connected}] {PROMPT} ", end='')
        sys.stdout.flush()


        while not (USER_QUIT or SYS_QUIT):

            if USER_SQL:
                send_repl_line(USER_SQL)
                USER_SQL =""
                pglite.interactive_one()

            inputs = [self.__clientSocket]
            outputs = []

            if len(clientData) > 0:
                outputs.append(self.__clientSocket)

            try:
                inputsReady, outputsReady, errorsReady = select.select(inputs, outputs, [], 0.016)
            except ValueError:
                break # fd -1
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
                            print("\n\n# 190: ECONNRESET")
                            terminate = True
                            break


            data = pump()
            if data and len(data) > 0:
                clientData += data

            if targetHostData:
                outputsReady.append("pglite")

            bytesWritten = 0

            for out in outputsReady:
                if out == self.__clientSocket and (len(clientData) > 0):
                    print(hexc(clientData, way="s>c", lines=25))
                    while clientData:
                        try:
                            bytesWritten = self.__clientSocket.send(clientData) # or len(clientData)
                            if bytesWritten>0:
                                clientData = clientData[bytesWritten:]
                        except BlockingIOError:
                            await asyncio.sleep(0)
                        except BrokenPipeError:
                            print("connection reset")
                            return

                elif out == "pglite" and (len(targetHostData) > 0):
                    PKT_NUM+=1
                    pglite.use_wire(1)
                    bytesWritten = len(targetHostData)
                    print(hexc(targetHostData, way=f"c>s: unixsocket[#{self.cid}] -> pglite #{PKT_NUM} ", lines=25))

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
                try:
                    pglite.interactive_one()
                except Exception as e:
                    sys.print_exception(e)
                    print("======================== custom ex ===============================")
                    pglite.clear_error()
                    if os.path.isfile(SINPUT):
                        print("======================== socket reset ===========================")
                        os.unlink(SINPUT)
                    pglite.interactive_write(-1)
                    print("======================== error cleared ===========================")
                    pglite.use_wire(1)
                    pglite.interactive_one()
                    print("======================== /custom ex ===============================")

            if terminate:
                break

            state = pglite.pgl_closed()
            if not state:
                print(f" ------------ pgl {state=} #{self.cid=} ----------------")
                self.__clientSocket.close()
            await asyncio.sleep(0.0)

        print(f"Client [#{self.cid}] task terminating")
        self.__clientSocket.close()
        Client.connected -= 1

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

REPL_BUF = []


def send_repl_line(line):
    pglite.use_wire(0)
    line = line.rstrip("\r\n; ") + ";"
    print(f"""------ REPL -------
{line}
-------------------
""")
    sql_bytes_cstring = line.encode("utf-8") + b"\0"  # <- do not forget this one, wasmtime won't add anything!
    pglite.Memory.mpoke(1, sql_bytes_cstring)


async def tests():
    global DONE
    for line in TESTS.split(";\n\n"):
        await asyncio.sleep(0.5)
        if line.strip():
            send_repl_line(line)
    await asyncio.sleep(0.5)
    DONE = 1



class i32(int):
    pass

class i64(int):
    pass


def sched_yield() -> i32:
    print("@@@@@@@@@@@@@@@@@@@@@@@@@@@@ sched_yield @@@@@@@@@@@@@@@@@@@@@@@@@@@@@@")
    return 0


async def repl():
    global REPL_BUF, USER_SQL, USER_QUIT, SYS_QUIT, PROMPT
    while not SYS_QUIT:
        if len(REPL_BUF):
            sql = await ainput(f"[{Client.connected}] ... ")
        else:
            sql = await ainput(f"[{Client.connected}] {PROMPT} ")
        sql = sql.decode().strip()
        if sql.strip().lower() == "q":
            USER_QUIT = True
            return

        multi_test = sql.strip().rstrip(';')

        if not multi_test:
            continue

        if multi_test == 'help':
            print("?: pg_dump -v ! pg_dump exec or enter sql")

        if multi_test == '?':
            imports = {
                'wasm32_wasi_preview1' : {
                    'sched_yield': sched_yield,
                }
            }

            pg_dump(pg_dump_bin, imports, ('--help',) )
            continue

        if multi_test == '!':
            pass


        if multi_test.endswith(' $$'):
            REPL_BUF.append(sql)
            continue

        if len(REPL_BUF):
            REPL_BUF.append(sql)
            if multi_test != '$$':
                continue

            sql = '\n'.join(REPL_BUF)
            REPL_BUF.clear()

        USER_SQL = sql

        if not Client.connected:
            # do REPL
            send_repl_line(USER_SQL)
            USER_SQL =""
            pglite.interactive_one()








async def main():
    global DONE


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

    if not USE_CMA:

        asyncio.get_running_loop().create_task(tests())

        # wait above test finished before accept connections
        while True:
            if DONE:
                break
            pglite.interactive_one()
            await asyncio.sleep(0.016)



    print("""

Server is listening for 1 incoming connection in non-blocking mode ...
Type sql command or 'q' and validate to quit ...

""")

    # do not block into socket server, we want to handle REPL I/O too.
    server.setblocking(0)


    # start repl in background
    asyncio.get_running_loop().create_task(repl())

    idlet = 0.016

    while not USER_QUIT:
        try:
            connection, client_address = server.accept()
            FD = connection.fileno()
            asyncio.create_task( Client(connection, "127.0.0.1", 5432).run() )
        except BlockingIOError:
            if not Client.connected:
                if os.path.isfile(SLOCK):
                    print(f"WASI client detected on {SLOCK}, serving with a busy loop")
                    pglite.interactive_one()
                    idlet = 0
                else:
                    idlet = 0.016
        await asyncio.sleep(idlet)


    server.close()

await main()

print('\r\nCleaning up temp files')
import glob

for temp in (*glob.glob('tmp/initdb.*.txt'),*glob.glob('tmp/PostgreSQL*'),):
    print( temp )
    os.unlink(temp)



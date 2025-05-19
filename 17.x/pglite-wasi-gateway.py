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

from pglite_wasi_import import wasm_import, is_file, poke, ainput, get_io_base_path, hexc, SI

options = {
    "REPL": "N",
    "PGUSER": "postgres",
    "PGDATABASE": "template1",
    "PREFIX": "/tmp/pglite",
}



if is_file("/tmp/fs/tmp/pglite/bin/pglite.wasi"):
    print("  ========== devel version =============")
    wasi_bin = "/tmp/fs/tmp/pglite/bin/pglite.wasi"
else:
    print("  -------- demo version ----------")
    wasi_bin = "tmp/pglite/bin/pglite.wasi"
print(f"{wasi_bin = }")
await wasm_import("pglite", wasi_bin, **options)

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

{SI(pglite.Memory.data_len)=} <= with included {pglite.get_buffer_size(0)} MiB shared memory

{pglite=}

"""
)

for k in dir(pglite):
    print("\t", k)


def dbg(code, data):
    fit = int(100 / 2)
    if len(data) > (fit * 2):
        print(code, len(data), data[:fit], "...", data[-fit:])
    else:
        print(code, str(len(data)).zfill(2), data)


class Client:
    cids = 0

    def __init__(self, clientSocket, targetHost, targetPort):
        self.__class__.cids += 1
        self.cid = self.cids
        self.__clientSocket = clientSocket
        print(f'\t[[[[  New client [{self.cid}] connection started', clientSocket, targetHost, targetPort, ' ]]]]')

    async def run(self):
        global pglite, CMA_QUERY, USER_SQL, PKT_NUM

        # initial clean up
        for f in [SINPUT, CINPUT]:
            try:
                os.remove(f)
                print(f"removed {f}")
            except:
                pass

        if not USE_CMA:

            def pump():
                global CLOCK_in_progress
#                print('-pump-', 'eof')
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

        else:
            def pump():
                global CMA_QUERY
                reply = pglite.interactive_read()
#                print('-pump-', reply)
                if reply:
                    # print( pglite.Memory.mpeek(0, CMA_QUERY+3+reply) )
                    cdata = bytes( pglite.Memory.mpeek(2+CMA_QUERY,CMA_QUERY+2+reply) )
                    print(f"pglite -> socket [{self.cid}], reply length {reply} at {CMA_QUERY+3}:")
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
                            print("\n\n# 190: ECONNRESET")
                            terminate = True
                            break


            data = pump()
            if data and len(data) > 0:
                clientData += data
                if 0:
                    print("@@@@@ INJECTION")
                    if PKT_NUM==3:
                        clientData += bytes([0x5a, 0x00, 0x00, 0x00, 0x05, 0x49])


            if targetHostData:
                outputsReady.append("pglite")

            bytesWritten = 0

            for out in outputsReady:
                if out == self.__clientSocket and (len(clientData) > 0):
                    print(hexc(clientData, way="s>c", lines=25))

                    try:
                        #bytesWritten = self.__clientSocket.sendall(clientData) or len(clientData)
                        bytesWritten = self.__clientSocket.send(clientData) # or len(clientData)
                    except BrokenPipeError:
                        print("connection reset")
                        return
                    if bytesWritten > 0:
                        clientData = clientData[bytesWritten:]
                        if 0:
                            if PKT_NUM==3:
                                print("\n\n\n@@@@@ INJECTION CLOSE")
                                self.__clientSocket.close()
                                terminate = True
                                break
                            if PKT_NUM==9:
                                print("\n\n\n@@@@@ INJECTION EMPTY")
                                self.__clientSocket.sendall(b'')

                elif out == "pglite" and (len(targetHostData) > 0):
                    PKT_NUM+=1
                    pglite.use_wire(1)
                    bytesWritten = len(targetHostData)
                    print(hexc(targetHostData, way=f"c>s: unixsocket[{self.cid}] -> pglite #{PKT_NUM} ", lines=25))

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
                    pglite.use_wire(1)
                    pglite.interactive_write(0)
                    pglite.interactive_one()
                    print("======================== custom ex ===============================")

            if terminate:
                break

            state = pglite.pgl_closed()
            if not state:
                print(f" ------------ pgl {state=} {self.cid=} ----------------")
                self.__clientSocket.close()
            await asyncio.sleep(0.016)

        print("Client [{self.cid}] task terminating")
        self.__clientSocket.close()

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

        # asyncio.get_running_loop().create_task(repl())

    print("Server is listening for incoming connections in non blocking mode ...")

    server.setblocking(0)

    while not USER_QUIT:
        try:
            connection, client_address = server.accept()
            FD = connection.fileno()
            asyncio.create_task( Client(connection, "127.0.0.1", 5432).run() )
        except BlockingIOError:
            await asyncio.sleep(0.016)

    server.close()

await main()

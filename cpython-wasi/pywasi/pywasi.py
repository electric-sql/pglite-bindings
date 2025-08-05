# https://github.com/WebAssembly/wasm-c-api

import asyncio
import sys
import os

reqs = ['aiohttp']



if os.environ.get('pywasi_vm', 'wasmtime'):
    reqs.append('wasmtime')
else:
    reqs.append('pywasm')


def pip_install(pkg, fqn=''):
    try:
        __import__(pkg)
    except:
        os.system(f'"{sys.executable}" -m pip install --user {fqn or pkg}')
        __import__("importlib").invalidate_caches()
    return __import__(pkg)

for req in reqs:
    try:
        vars()[req] = pip_install(req)
    except Exception as e:
        vars()[req] = None
        print(f'failed to install {req} reason:',e)

if wasmtime:
    os.environ['pywasi_vm'] = 'wasmtime'
    #from wasmtime import WasiConfig, Linker, Engine, Store, Module
    sys.modules['pywasi_vm'] = wasmtime
    WIP = False
else:
    os.environ['pywasi_vm'] = 'pywasm'
    #from .pywasm import WasiConfig, Linker, Engine, Store, Module
    from . import pywasm
    WIP = True
    sys.modules['pywasi_vm'] = pywasm


ROOTFS = None


class i32(int):
    pass


class i64(int):
    pass



def set_fs(base):
    global ROOTFS
    if not isinstance(base, str):
        ROOTFS = base.as_posix()
    else:
        ROOTFS = base
    print(f"{ROOTFS=}")



    class wasi_import:
        import os

        current = None

        os.environ["WASMTIME_BACKTRACE_DETAILS"] = "1"

        class __module:

            def __init__(self, vm, wasmfile):
                if not isinstance(wasmfile, str):
                    self.wasmfile = wasmfile.as_posix()
                else:
                    self.wasmfile = wasmfile
                self.store = vm.store
                self.module = vm.Module.from_file(vm.linker.engine, self.wasmfile)
                if WIP:
                    raise SystemExit

                self.instance = vm.linker.instantiate(self.store, self.module)

                self.mem = self.instance.exports(self.store)["memory"]

            def _start(self):
                try:
                    self.get("_start")()
                except Exception as e:
                    if repr(e).find('sdk_exit'):
                        ec = self.mem.read(self.store, 1,2)[0]
                        print(f"{self.wasmfile}:EXIT({ec})")
                        return ec
                    raise
                return 0


            def get(self, export):

                call = self.instance.exports(self.store)[export]
                store = self.store

                def bound(*argv, **env):
                    return call(store, *argv, **env)

                return bound

            def __all__(self):
                return list(wasm_mod.instance.exports(wasm_mod.store).keys())

            def __repr__(self):
                return self.wasmfile

        #  #, Instance, Trap, MemoryType, Memory, Limits, WasmtimeError
        from pywasi_vm import WasiConfig, Linker, Engine, Store, Module

        # overload
        from pywasi_vm import Func, FuncType, ValType



        with open("dev/urandom", "wb") as rng_out:
            rng_out.write(os.urandom(128))






        def __init__(self, alias, wasmfile, imports={}, argv=(), **env):
            config = self.WasiConfig()

            config.inherit_stdout()
            config.inherit_stderr()

            if ROOTFS is None:
                raise Exception('FS base was not set, use .set_fs(path)')

            config.preopen_dir(ROOTFS, "/tmp")
            if not os.path.isdir("dev"):
                os.mkdir("dev")


            config.preopen_dir("dev", "/dev")

            linker = self.Linker(self.Engine())

            linker.define_wasi()

            store = self.Store(linker.engine)

            self.config = config
            self.linker = linker
            self.store = store

            self.env = [
                ["ENVIRONMENT", "wasm32_wasi_preview1"],
            ]

            self.config.argv = [wasmfile] + list(argv)
            # config.inherit_argv()
            # config.inherit_env()


            for k, v in env.items():
                self.env.append([k, v])
            self.config.env = self.env
            self.store.set_wasi(self.config)

            py_mod = type(sys)(alias)

            for ns in imports:
                print(ns)
                for fn_name in imports[ns]:
                    self.set(imports[ns][fn_name], ns=ns, name=fn_name)


            wasm_mod = self.__module(self, wasmfile)

            # if exitcode == 0 finish build interface
            if not wasm_mod._start():
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


        def set(self, func, ns='wasi_snapshot_preview1', name=''):
            name = name or func.__name__
            self.linker.allow_shadowing = True
            mapping = {
                'wasm32_wasi_preview1' : 'wasi_snapshot_preview1',
            }
            rt = []
            ann = func.__annotations__
            t = ann.get('return', None)
            if t:
                rt.append( getattr(self.ValType, t.__name__)() )
            else:
                rt=    [self.ValType.i32()]
            func_link = self.Func(self.store, self.FuncType([], rt), func)
            print(f"    Linking {ns}.{name} to {func}")
            self.linker.define(self.store, mapping.get(ns,ns), name, func_link)



    return wasi_import

print(f"""

{os.environ['pywasi_vm']=}

{sys.modules['pywasi_vm']=}

""")



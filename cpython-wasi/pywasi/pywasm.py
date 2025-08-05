
import pywasm

class WasiConfig:

    argv = []
    env = []

    def inherit_stdout(self):
        pass
    def inherit_stderr(self):
        pass
    def preopen_dir(self, real, mountpoint):
        pass


class Engine(pywasm.core.Runtime):
    pass


class Store:
    def __init__(self, vm:Engine):
        print(self, 'created')

    def set_wasi(self, config : WasiConfig):
        print('set_wasi: config argv/env set')
        self.config = config


class Module:

    @classmethod
    def from_file(cls, vm:Engine, wasmfile ):
        instance = vm.instance_from_file(wasmfile)
        module = cls()
        module.instance = instance
        module.vm = vm
        module.wasmfile = wasmfile
        print('instantiating:', wasmfile, module)
        return module

class Linker:
    def __init__(self, vm:Engine):
        self.engine = vm

    def define_wasi(self):
        print("wasi mode")

    def instantiate(self, store: Store, module:Module):
        print(store)
        print(store.config)
        print(module)
        print(module.instance)


if __name__ == '__main__':

    # wasm32_wasi_preview1
    async def main(wasi, runtime: pywasm.core.Runtime, module: pywasm.core.ModuleInst) -> int:
        # Attempt to begin execution of instance as a wasi command by invoking its _start() export. If instance does
        # not contain a _start() export, then an exception is thrown.
        try:
            await runtime.async_invocate(module, '_start', [])
        except Exception as e:
            runtime.machine.stack.frame.clear()
            runtime.machine.stack.label.clear()
            runtime.machine.stack.value.clear()
            if len(e.args) >= 1 and e.args[0] == SystemExit:
                return e.args[1]
            raise e
        else:
            return 0
        finally:
            for e in wasi.fd[wasi.FD_STDERR + 1:]:
                if e.wasm_type == wasi.FILETYPE_CHARACTER_DEVICE:
                    continue
                if e.host_status != wasi.FILE_STATUS_CLOSED:
                    os.close(e.host_fd)
                    e.host_status = wasi.FILE_STATUS_CLOSED

    print(pywasm.__file__)

    pywasm.VM = pywasm.core.Runtime()

    cwd = os.getcwd()

    #wasi.fd[1].pipe = io.BytesIO(bytearray())
    #wasi.bind(runtime)
    #exit = wasi.main(runtime, runtime.instance_from_file(wasm_path))
        #wasi.fd[1].pipe.seek(0)
    print(f"{sys.argv=}")
    exe = ''
    while sys.argv and not exe.find('.was')>0:
        exe = sys.argv.pop(0)

    if exe.startswith("/"):
        argv = [exe]
    else:
        argv = [cwd+"/"+exe]

    argv.extend(sys.argv)

    print(f"{argv=}")
    fs = {
        # This object represents the WebAssembly application's local directory structure. The string keys of dirs are
        # treated as directories within the file system. The corresponding values in preopens are the real paths to those
        # directories on the host machine.
        '/': cwd,
        '.': cwd,
        './' : cwd,
    }

    env = { 'HOME' : "/tmp" }
    wasm32_wasi_preview1 = pywasm.wasi.Preview1(argv, fs, env )

    wasm32_wasi_preview1.bind(pywasm.VM)
    #wasm32_wasi_preview1.main(pywasm.VM, pywasm.VM.instance_from_file(argv[0]))
    asyncio.run( main(wasm32_wasi_preview1, pywasm.VM, pywasm.VM.instance_from_file(argv[0])) )



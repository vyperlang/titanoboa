from ipykernel.kernelbase import Kernel
from ipykernel.kernelapp import IPKernelApp

from vyper.ast.utils import parse_to_ast
from vyper.semantics.namespace import Namespace


# TO RUN:
# copy kernel.json into ~/.venvs/boa/share/jupyter/kernels/vyper (or whatever directory looks reasonable from `jupyter kernelspec list`)
# run: jupyter console --kernel vyper

class VyperKernel(Kernel):
    implementation = 'Vyper'
    implementation_version = '1.0'
    language = 'vyper'
    language_version = '0.1'
    language_info = {'mimetype': 'text/plain'}
    banner = "Vyper REPL\n"

    _vy_ns = None

    @property
    def vy_ns(self):
        if self._vy_ns is None:
            self._vy_ns = Namespace()
        return self._vy_ns

    def do_execute(self, code, silent, store_history=True, user_expressions=None,
                   allow_stdin=False):
        ast = parse_to_ast(code)
        with override_namespace(self.vy_ns):
            vy_ast.folding.fold(ast)
            validation.add_module_namespace(ast, ifaces)  # ?
            validation.validate_functions(ast)

        # idea is: check ast.body[0] type. 
        # if FunctionDef:
        #   add function to namespace
        # if Stmt:
        #   execute it in contract context?
        # if Expr:
        #   eval (in contract context?) and return
        # what about unbound variables?

        if not silent:
            res = code
            payload = {'name': 'stdout', 'text': res}
            self.send_response(self.iopub_socket, 'stream', payload)

        return {'status': 'ok',
                # The base class increments the execution count
                'execution_count': self.execution_count,
                'payload': [],
                'user_expressions': {},
               }


if __name__ == '__main__':
    IPKernelApp.launch_instance(kernel_class=VyperKernel)

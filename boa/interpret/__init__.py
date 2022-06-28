from vyper.compiler.phases import CompilerData

from boa.interpret.context import InterpreterContext
from boa.interpret.stmt import interpret_block
from boa.interpret.object import VyperObject

class VyperFunction:
    def __init__(self, fn_ast, global_ctx, contract):
        self.fn_ast = fn_ast
        self.ctx = InterpreterContext(global_ctx, contract)

    def __call__(self, *args, **kwargs):
        #self.ctx.set_args(self.*args)
        #self.ctx.set_kwargs(**kwargs)

        return interpret_block(self.fn_ast.body, self.ctx)

class VyperContract:
    def __init__(self, global_ctx):
        self.global_ctx = global_ctx

        functions = {fn.name: fn for fn in global_ctx._function_defs}

        for fn in global_ctx._function_defs:
            setattr(self, fn.name, VyperFunction(fn, global_ctx, self))

        for k, v in global_ctx._globals.items():
            setattr(self, k, VyperObject(None, v.typ))

def load(filename: str) -> VyperContract:
    with open(filename) as f:
        data = CompilerData(f.read())

    return VyperContract(data.global_ctx)

from boa.interpret.context import InterpreterContext
from boa.interpret.stmt import interpret_block
from boa.interpret.object import VyperObject
from vyper.ast.signatures.function_signature import FunctionSignature

class VyperFunction:
    def __init__(self, fn_ast, global_ctx, contract):
        self.fn_ast = fn_ast
        self.fn_signature = FunctionSignature.from_definition(fn_ast, global_ctx)
        self.ctx = InterpreterContext(global_ctx, contract)

    def __repr__(self):
        return repr(self.fn_ast)

    def __call__(self, *args, **kwargs):
        if len(args) != len(self.fn_signature.base_args):
            raise Exception(f"bad args to {self}")

        for arg_ast, argval in zip(self.fn_signature.base_args, args):
            val = VyperObject(argval, typ=arg_ast.typ)
            self.ctx.set_var(arg_ast.name, val)

        sig_kwarg_types = {arg.name: arg.typ for arg in self.fn_signature.default_args}
        sig_kwargs = self.fn_signature.default_values.copy()
        for k, val in kwargs.items():
            val = VyperObject(val, typ=sig_kwarg_types[k])
            self.ctx.set_var(arg_ast.name, val)
            sig_kwargs.pop(arg_ast.name)
        for k, val in sig_kwargs:
            val = VyperObject(val, typ=sig_kwarg_types[k])
            self.ctx.set_var(arg_ast.name, val)

        return interpret_block(self.fn_ast.body, self.ctx)

class VyperContract:
    def __init__(self, global_ctx):
        self.global_ctx = global_ctx

        functions = {fn.name: fn for fn in global_ctx._function_defs}

        for fn in global_ctx._function_defs:
            setattr(self, fn.name, VyperFunction(fn, global_ctx, self))

        for k, v in global_ctx._globals.items():
            setattr(self, k, VyperObject.empty(v.typ))

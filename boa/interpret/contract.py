from boa.interpret.context import InterpreterContext
from boa.interpret.stmt import interpret_block
from boa.interpret.object import VyperObject
from vyper.ast.signatures.function_signature import FunctionSignature
from boa.vm import Env
import eth.constants as constants
from vyper.codegen.module import generate_ir_for_module
from vyper.codegen.core import calculate_type_for_external_return
from vyper.codegen.types.types import TupleType
from vyper.utils import cached_property, keccak256
import eth_abi as abi


class VyperContract:
    def __init__(self, compiler_data):
        self.compiler_data = compiler_data
        global_ctx = compiler_data.global_ctx
        self.global_ctx = global_ctx
        self.env = Env()
        # TODO actually mock an address (or just deploy)
        self.address = constants.ZERO_ADDRESS

        functions = {fn.name: fn for fn in global_ctx._function_defs}


        for fn in global_ctx._function_defs:
            setattr(self, fn.name, VyperFunction(fn, self))

    @cached_property
    def bytecode_runtime(self):
        return self.compiler_data.bytecode_runtime

class VyperFunction:
    def __init__(self, fn_ast, contract):
        self.fn_ast = fn_ast
        self.contract = contract
        self.env = contract.env

        # could be cached_property
        self.fn_signature = FunctionSignature.from_definition(fn_ast, contract.global_ctx)

    def __repr__(self):
        return repr(self.fn_ast)

    # hotspot, cache the signature computation
    def args_abi_type(self, num_kwargs):
        if not hasattr(self, "_signature_cache"):
            self._signature_cache = {}
        if num_kwargs in self._signature_cache:
            return self._signature_cache[num_kwargs]

        # align the kwargs with the signature
        sig_kwargs = self.fn_signature.default_args[:num_kwargs]
        sig_args = self.fn_signature.base_args + sig_kwargs
        args_abi_type = "(" + ",".join(arg.typ.abi_type.selector_name() for arg in sig_args) + ")"
        method_id = keccak256(bytes(self.fn_signature.name + args_abi_type, "utf-8"))[:4]
        self._signature_cache[num_kwargs] = (method_id, args_abi_type)

        return method_id, args_abi_type

    # hotspot, cache the signature computation
    @cached_property
    def return_abi_type(self):
        return_typ = calculate_type_for_external_return(self.fn_signature.return_type)
        return return_typ.abi_type.selector_name()

    def __call__(self, *args, **kwargs):
        if len(args) != len(self.fn_signature.base_args):
            raise Exception(f"bad args to {self}")

        # align the kwargs with the signature
        sig_kwargs = self.fn_signature.default_args[:len(kwargs)]

        method_id, args_abi_type = self.args_abi_type(len(kwargs))

        encoded_args = abi.encode_single(args_abi_type, args)
        calldata_bytes = method_id + encoded_args

        computation = self.env.execute_code(bytecode=self.contract.bytecode_runtime, data=calldata_bytes)

        if computation.is_error:
            # TODO intercept and show source location
            raise computation.error

        ret = abi.decode_single(self.return_abi_type, computation.output)

        # unwrap the tuple if needed
        if not isinstance(self.fn_signature.return_type, TupleType):
            ret, = ret

        return VyperObject(ret, typ=self.fn_signature.return_type)

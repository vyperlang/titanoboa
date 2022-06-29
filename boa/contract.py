import eth_abi as abi
from vyper.ast.signatures.function_signature import FunctionSignature
from vyper.codegen.core import calculate_type_for_external_return
from vyper.codegen.types.types import TupleType
from vyper.utils import cached_property, keccak256

from boa.env import Env
from boa.object import VyperObject


class VyperContract:
    def __init__(self, compiler_data, *args, env=None):
        self.compiler_data = compiler_data
        global_ctx = compiler_data.global_ctx
        self.global_ctx = global_ctx

        if env is None:
            env = Env.get_singleton()

        # honestly what the fuck
        class NoMeteringComputation(env.vm.state.computation_class):
            def consume_gas(self, amount, reason):
                pass

            def refund_gas(self, amount):
                pass

            def return_gas(self, amount):
                pass

        self.env = env

        self.env.vm.state.computation_class = NoMeteringComputation

        self.address = self._generate_address()

        encoded_args = b""

        self.bytecode = self.env.deploy_code(
            bytecode=self.compiler_data.bytecode + encoded_args, deploy_to=self.address
        )

        for fn in global_ctx._function_defs:
            setattr(self, fn.name, VyperFunction(fn, self))

        self._computation = None

    def _generate_address(self):
        # generates mock address; not same as actual create
        return self.env.generate_address()


class VyperFunction:
    def __init__(self, fn_ast, contract):
        self.fn_ast = fn_ast
        self.contract = contract
        self.env = contract.env

        # could be cached_property
        self.fn_signature = FunctionSignature.from_definition(
            fn_ast, contract.global_ctx
        )

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
        args_abi_type = (
            "(" + ",".join(arg.typ.abi_type.selector_name() for arg in sig_args) + ")"
        )
        method_id = keccak256(bytes(self.fn_signature.name + args_abi_type, "utf-8"))[
            :4
        ]
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
        # sig_kwargs = self.fn_signature.default_args[: len(kwargs)]

        method_id, args_abi_type = self.args_abi_type(len(kwargs))

        encoded_args = abi.encode_single(args_abi_type, args)
        calldata_bytes = method_id + encoded_args

        computation = self.env.execute_code(
            bytecode=self.contract.bytecode, data=calldata_bytes
        )
        self.contract._computation = computation  # for further inspection

        computation.raise_if_error()  # TODO intercept and show source location

        ret = abi.decode_single(self.return_abi_type, computation.output)

        # unwrap the tuple if needed
        if not isinstance(self.fn_signature.return_type, TupleType):
            (ret,) = ret

        return VyperObject(ret, typ=self.fn_signature.return_type)

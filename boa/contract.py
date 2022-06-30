import eth_abi as abi
from vyper.ast.signatures.function_signature import FunctionSignature
from vyper.codegen.core import calculate_type_for_external_return
from vyper.codegen.types.types import TupleType
from vyper.compiler.output import build_source_map_output
from vyper.exceptions import VyperException  # for building source traces
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

        self.env = env
        self.address = self.env.generate_address()

        encoded_args = b""

        fns = {fn.name: fn for fn in global_ctx._function_defs}

        if "__init__" in fns:
            ctor = VyperFunction(fns.pop("__init__"), self)
            encoded_args = ctor._prepare_calldata(*args)
            encoded_args = encoded_args[4:]  # strip method_id

        self.bytecode = self.env.deploy_code(
            bytecode=self.compiler_data.bytecode + encoded_args, deploy_to=self.address
        )

        for fn in fns.values():
            setattr(self, fn.name, VyperFunction(fn, self))

        self._computation = None

    @cached_property
    def source_map(self):
        return build_source_map_output(self.compiler_data)

    def find_source_of(self, code_stream):
        pc_map = self.source_map["pc_pos_map"]
        for pc in reversed(code_stream._trace):
            if pc in pc_map:
                return pc_map[pc]

        raise Exception(f"Couldn't find source for {code_stream.program_counter}")


class BoaError(VyperException):
    pass


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
        if self.fn_signature.return_type is None:
            return None

        return_typ = calculate_type_for_external_return(self.fn_signature.return_type)
        return return_typ.abi_type.selector_name()

    def _prepare_calldata(self, *args, **kwargs):
        if len(args) != len(self.fn_signature.base_args):
            raise Exception(f"bad args to {self}")

        # align the kwargs with the signature
        # sig_kwargs = self.fn_signature.default_args[: len(kwargs)]

        method_id, args_abi_type = self.args_abi_type(len(kwargs))

        encoded_args = abi.encode_single(args_abi_type, args)
        return method_id + encoded_args

    def __call__(self, *args, **kwargs):
        calldata_bytes = self._prepare_calldata(*args, **kwargs)
        computation = self.env.execute_code(
            to_address=self.contract.address,
            bytecode=self.contract.bytecode,
            data=calldata_bytes,
        )
        self.contract._computation = computation  # for further inspection

        if computation.is_error:
            raise BoaError(
                repr(computation.error), self.contract.find_source_of(computation.code)
            )

        if self.return_abi_type is None:
            return None

        ret = abi.decode_single(self.return_abi_type, computation.output)

        # unwrap the tuple if needed
        if not isinstance(self.fn_signature.return_type, TupleType):
            (ret,) = ret

        return VyperObject(ret, typ=self.fn_signature.return_type)

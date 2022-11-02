import eth_abi as abi
from cached_property import cached_property

from vyper.codegen.function_definitions import generate_ir_for_function
from vyper.codegen.ir_node import IRnode
from vyper.compiler import output as compiler_output
from vyper.ir import compile_ir as compile_ir
from vyper.ir.optimizer import optimize
from vyper.utils import abi_method_id

from boa.vyper import _METHOD_ID_VAR
from boa.vyper.compiler_utils import generate_bytecode_for_internal_fn


class VyperFunction:
    def __init__(self, fn_ast, contract):
        self.fn_ast = fn_ast
        self.contract = contract
        self.env = contract.env

    def __repr__(self):
        return repr(self.fn_ast)

    @cached_property
    def fn_signature(self):
        return self.contract.compiler_data.function_signatures[self.fn_ast.name]

    @cached_property
    def ir(self):
        # patch compiler_data to have IR for every function
        sigs = self.contract._sigs
        global_ctx = self.contract.global_ctx

        ir = generate_ir_for_function(self.fn_ast, sigs, global_ctx, False)
        return optimize(ir)

    @cached_property
    def assembly(self):
        ir = IRnode.from_list(
            ["with", _METHOD_ID_VAR, ["shr", 224, ["calldataload", 0]], self.ir]
        )
        return compile_ir.compile_to_assembly(ir)

    @cached_property
    def opcodes(self):
        return compiler_output._build_opcodes(self.bytecode)

    @cached_property
    def bytecode(self):
        bytecode, _ = compile_ir.assembly_to_evm(self.assembly)
        return bytecode

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
        method_id = abi_method_id(self.fn_signature.name + args_abi_type).to_bytes(
            4, "big"
        )
        self._signature_cache[num_kwargs] = (method_id, args_abi_type)

        return method_id, args_abi_type

    def _prepare_calldata(self, *args, **kwargs):
        if (
            not len(self.fn_signature.base_args)
            <= len(args)
            <= len(self.fn_signature.args)
        ):
            raise Exception(f"bad args to {self}")

        # align the kwargs with the signature
        # sig_kwargs = self.fn_signature.default_args[: len(kwargs)]

        total_non_base_args = len(kwargs) + len(args) - len(self.fn_signature.base_args)
        method_id, args_abi_type = self.args_abi_type(total_non_base_args)

        # allow things with `.address` to be encode-able
        args = [getattr(arg, "address", arg) for arg in args]

        encoded_args = abi.encode_single(args_abi_type, args)
        return method_id + encoded_args

    def __call__(self, *args, value=0, gas=None, **kwargs):
        calldata_bytes = self._prepare_calldata(*args, **kwargs)
        computation = self.env.execute_code(
            to_address=self.contract.address,
            bytecode=self.contract.bytecode,
            data=calldata_bytes,
            value=value,
            gas=gas,
        )

        typ = self.fn_signature.return_type
        return self.contract.marshal_to_python(computation, typ)


class VyperInternalFunction(VyperFunction):
    """Internal contract functions are exposed by wrapping it with a dummy
    external contract function, which involves changing the contract's
    bytecode.

    TBD: add VyperContract.eval and VyperContract.compile_stmt inspired
    methods here to wrap internal function with external function.
    """

    @cached_property
    def bytecode(self):
        """We overwrite some bytecode here"""
        bytecode, _, _ = generate_bytecode_for_internal_fn(self)
        return bytecode

    def __call__(self, *args, value=0, gas=None, **kwargs):

        calldata_bytes = self._prepare_calldata(*args, **kwargs)
        computation = self.env.execute_code(
            to_address=self.contract.address,
            bytecode=self.bytecode,  # <- overwritten bytecode used here
            data=calldata_bytes,
            value=value,
            gas=gas,
        )

        typ = self.fn_signature.return_type
        return self.contract.marshal_to_python(computation, typ)

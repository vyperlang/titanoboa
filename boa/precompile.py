from typing import Any

from vyper.ast import parse_to_ast
from vyper.builtins._signatures import BuiltinFunctionT
from vyper.builtins.functions import DISPATCH_TABLE, STMT_DISPATCH_TABLE
from vyper.builtins.functions import abi_encode as abi_encode_ir
from vyper.builtins.functions import ir_tuple_from_args, process_inputs
from vyper.codegen.core import IRnode, needs_external_call_wrap
from vyper.evm.address_space import MEMORY
from vyper.semantics.analysis.base import VarInfo
from vyper.semantics.namespace import get_namespace
from vyper.semantics.types import TupleT
from vyper.semantics.types.function import ContractFunctionT
from vyper.utils import keccak256

from boa.util.abi import abi_decode, abi_encode
from boa.vm.py_evm import register_raw_precompile


class PrecompileBuiltin(BuiltinFunctionT):
    def __init__(self, name, args, return_type, address):
        # override BuiltinFunctionT attributes
        self._id = name
        self._inputs = args  # list[tuple[str, VyperType]]
        self._return_type = return_type

        # set the precompile address
        self._address = address

    @process_inputs
    def build_IR(self, expr, args, kwargs, context):
        # allocate buffer for data to pass to precompile
        ret_buf = context.new_internal_variable(self._return_type)

        # allocate args buffer
        args_as_tuple = ir_tuple_from_args(args)
        args_abi_t = args_as_tuple.typ.abi_type
        args_buf = context.new_internal_variable(args_as_tuple.typ)

        ret = ["seq"]

        # store abi-encoded argument at buf
        args_len = abi_encode_ir(
            args_buf, args_as_tuple, context, args_abi_t.size_bound(), returns_len=True
        )
        ret_len = self._return_type.abi_type.size_bound()

        addr = int.from_bytes(self._address, "big")

        # call precompile
        ret.append(["staticcall", "gas", addr, args_buf, args_len, ret_buf, ret_len])
        ret += [ret_buf]

        return IRnode.from_list(ret, typ=self._return_type, location=MEMORY)


# takes a user-provided signature and produces shim code for
# serializing and deserializing
# ex. precompile("def foo() -> uint256")
def precompile(user_signature: str, force: bool = False) -> Any:
    def decorator(func):
        vy_ast = parse_to_ast(user_signature + ": view").body[0]
        func_t = ContractFunctionT.from_FunctionDef(vy_ast, is_interface=True)

        args_t = TupleT(tuple(func_t.argument_types))

        def wrapper(computation):
            # Decode input arguments from message data
            msg_data = computation.msg.data_as_bytes
            arg_values = abi_decode(args_t.abi_type.selector_name(), msg_data)

            # Call the original function with decoded input arguments
            res = func(*arg_values)

            return_t = func_t.return_type
            if return_t is not None:
                # Encode the result to be ABI-compatible
                # wrap to make it a tuple if necessary
                if needs_external_call_wrap(return_t):
                    res = (res,)
                    return_t = TupleT((return_t,))

                ret_abi_t = return_t.abi_type.selector_name()
                computation.output = abi_encode(ret_abi_t, res)

                return computation

        address = keccak256(user_signature.encode("utf-8"))[:20]
        register_raw_precompile(address, wrapper, force=force)

        args = [(arg.name, arg.typ) for arg in func_t.arguments]
        fn_name = func_t.name
        builtin = PrecompileBuiltin(fn_name, args, func_t.return_type, address)

        # sketchy check to see which dispatch table it should go in
        # ideally upstream vyper should be refactored to deal with this
        if func_t.return_type is not None:
            DISPATCH_TABLE[fn_name] = builtin
        else:
            STMT_DISPATCH_TABLE[fn_name] = builtin

        # yuck. note to refactor on vyper side.
        get_namespace()[fn_name] = VarInfo(builtin)

        return wrapper

    return decorator

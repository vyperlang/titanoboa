from typing import Optional
from eth.codecs import abi
from vyper.address_space import MEMORY
from vyper.ast import parse_to_ast
from vyper.codegen.core import IRnode
from vyper.semantics.types.user import type_from_abi
from vyper.semantics.types.utils import type_from_annotation
from vyper.utils import binascii
from boa.environment import register_precompile
from vyper.builtins.functions import DISPATCH_TABLE, abi_encode, add_ofst, ir_tuple_from_args, process_inputs
from vyper.builtins._signatures import BuiltinFunction
from vyper.codegen.core import IRnode
from vyper.semantics.types.shortcuts import (
    UINT256_T,
)

def extract_arg_types(signature: str):
    # Extract argument types and their names using regex

    args = signature.split("(")[1].split(")")[0].split(",")
    typs = [x.split(":")[1].strip().split("[")[0].lower() for x in args]
    names = [x.split(":")[0].strip().split("[")[0].lower() for x in args]

    # Combine the cleaned argument types and return them in parentheses
    return f"({','.join(typs)})", names

def parse_address_string(address: str | bytes) -> bytes:
    # Convert address string to bytes
    if isinstance(address, str):
        if address.startswith("0x"):
            address = address[2:]
        return bytes.fromhex(address)
    elif isinstance(address, bytes):
        return binascii.unhexlify(bytes(address.hex(), "utf-8").zfill(40))

class PrecompileBuiltin(BuiltinFunction):
    # id can be name
    _id = ""
    # list of inputs (parsed from signature)
    _inputs = []
    # return type (parsed from signature)
    _return_type = None
    _address = None

    def __init__(self, name: str, inputs, return_type, address):
        self._id = name
        self._inputs = inputs
        self._return_type = return_type
        self._address = address

    @process_inputs
    def build_IR(self, expr, args, kwargs, context):
        # allocate buffer for data to pass to precompile
        # we will pass 4-byte function selector and 32-byte argument
        buf = context.new_internal_variable(self._return_type)

        args_as_tuple = ir_tuple_from_args(args)
        args_abi_t = args_as_tuple.typ.abi_type

        ret = ["seq"]

        # store byte selector
        ret += [["mstore", buf, 0x12341234]]

        # store abi-encoded argument at buf+4
        length = abi_encode(buf + 4, args_as_tuple, context, args_abi_t.size_bound(), returns_len=True)

        MYPRINT_ADDRESS_STR = "0x" + str(self._address.hex().zfill(40))
        MYPRINT_ADDRESS = int(MYPRINT_ADDRESS_STR, 16)

        # call precompile
        ret.append(["staticcall",
                    "gas", # fwd all gas
                    MYPRINT_ADDRESS, # precompile address
                    buf, # argsOffset
                    add_ofst(length, 4), # abi-encoded length + byte selector
                    buf, # overwrite argsOffset with result
                    32 # return length
                    ])
        ret += [buf]

        return IRnode.from_list(ret, typ=self._return_type, location=MEMORY)

def precompile(signature: str, address: Optional[str | bytes] = None):
    def decorator(func):
        arg_types, names = extract_arg_types(signature)
        typs = [type_from_abi({"type": x}) for x in arg_types[1:-1].split(",")]
        inputs = list(zip(names, typs))
        vy_ast = parse_to_ast(signature + ":\n\tpass")
        return_type = type_from_annotation(vy_ast.body[0].returns)
        output_signature = signature.split("->")[1].strip()
        if not output_signature.startswith("("):
            output_signature = f"({output_signature})"

        def wrapper(computation):
            # Decode input arguments from message data
            message_data = computation.msg.data_as_bytes
            input_args = abi.decode(arg_types, message_data[4:])

            # Call the original function with decoded input arguments
            result = func(*input_args)

            # Encode the result to be ABI-compatible
            # wrap output_signature in parentheses to make it a tuple if it's not already
            computation.output = abi.encode(output_signature, [result])

            # Register the precompile with the given address if one is provided
            return computation

        if address:
            register_precompile(parse_address_string(address), wrapper)
            DISPATCH_TABLE["printmsg"] = PrecompileBuiltin("printmsg", inputs, return_type, address)

        return wrapper

    return decorator

@precompile("def printmsg(x: uint256, y: uint256) -> uint256", b'printuint256')
def printmsg(x: int, y: int):
    print(x)
    return x + y


# utils for making precompiles into builtins

import boa

from functools import wraps

 
def precompile(signature):

    ast = parse_to_ast(signature).body[0]
    ctx, = GlobalContext()
    fn_sig = FunctionSignature.from_definition(ast, ctx, interface_def=True)
    fn_typ = ContractFunction.from_FunctionDef(ast, is_interface=True)

    def s(inner):
        inner.fn_sig = fn_sig

        @wraps(f)
        def precompile_implementation(computation):
            # ex. (address,uint256)
            args_abi_sig = fn_type.base_signature[len(fn_sig.name):]
            args = abi.decode_single(args_abi_sig, computation.msg.data[4:])

            res = inner(computation, *args)

            typ = calculate_type_for_external_return(fn_sig.return_type)
            ret_abi_typ = typ.abi_type.selector_name()

            computation.output = abi.encode_single(ret_abi_typ, res)

            return computation

        return precompile_implementation

    return s

BOA_BUILTINS = {}
BOA_FAKE_OBJECT = InterfacePrimitive()

# TODO add force kwarg
def register_hl(f):
    BOA_BUILTINS[method_id(f.fn_sig.base_signature)] = f
    BOA_FAKE_OBJECT.add_member(f.fn_typ)

def boa_builtin_dispatcher(computation):
    # will throw KeyError if the builtin is not there
    f = BOA_BUILTINS[computation.msg.data[:4]]

    return f(computation)

# to_checksum_address(b"titanoboa".rjust(20, b"\x00"))
register_precompile("0x0000000000000000000000746974616e6F626f61", boa_builtin_dispatcher)

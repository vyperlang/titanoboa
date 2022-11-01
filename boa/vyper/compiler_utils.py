import textwrap

from vyper.ast.utils import parse_to_ast
from vyper.ast.signatures.function_signature import FunctionSignature
from vyper.codegen.function_definitions import generate_ir_for_function
from vyper.codegen.ir_node import IRnode
from vyper.ir import compile_ir as compile_ir
import vyper.semantics.validation as validation
from vyper.utils import abi_method_id

from boa.vyper import _METHOD_ID_VAR


def compile_stmt(wrapper_code, contract):
    """Compiles a wrapper code and appends it to the top of the IR of a
    contract. This is useful for vyper `eval` and internal functions, where
    the runtime bytecode must be changed to add more runtime functionality
    (such as eval, and calling internal functions)
    """

    compiler_data = contract.compiler_data
    global_ctx = contract.global_ctx
    ifaces = compiler_data.interface_codes
    ast = parse_to_ast(wrapper_code, ifaces)

    # override namespace and add wrapper code at the top
    with contract.override_vyper_namespace():
        validation.add_module_namespace(compiler_data, ifaces)
        validation.validate_functions(ast)

    ast = ast.body[0]
    sig = FunctionSignature.from_definition(ast, global_ctx)
    ast._metadata["signature"] = sig

    sigs = {"self": compiler_data.function_signatures}
    ir = generate_ir_for_function(ast, sigs, global_ctx, False)

    ir = IRnode.from_list(
        ["with", _METHOD_ID_VAR, abi_method_id(sig.base_signature), ir]
    )
    assembly = compile_ir.compile_to_assembly(ir, no_optimize=True)

    # extend IR with contract's unoptimized assembly
    assembly.extend(contract.unoptimized_assembly)
    compile_ir._optimize_assembly(assembly)
    bytecode, source_map = compile_ir.assembly_to_evm(assembly)
    bytecode += contract.data_section
    typ = sig.return_type

    return bytecode, source_map, typ


def generate_bytecode_for_internal_fn(fn):

    contract = fn.contract
    fn_args = fn.fn_signature.args
    fn_name = fn.fn_signature.name
    return_sig = fn.fn_signature.return_type
    fn_sig_parsed = ", ".join(
        [f"{arg.name}: {arg.typ}" for arg in fn_args]
    )
    fn_args_parsed = ", ".join(
        [f"{arg.name}" for arg in fn_args]
    )

    # TODO: add default values if they exist!
    wrapper_code = textwrap.dedent(
        f"""
                @external
                @payable
                def __boa_private_{fn_name}({fn_sig_parsed}) -> {return_sig}:
                    return self.{fn_name}({fn_args_parsed})
            """
    )

    return compile_stmt(wrapper_code, contract)

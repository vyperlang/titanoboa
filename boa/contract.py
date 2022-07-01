import copy
from dataclasses import dataclass
from typing import Any, Optional

import eth_abi as abi
import vyper.codegen.types.types as vyper
from vyper.ast.signatures.function_signature import FunctionSignature
from vyper.codegen.core import calculate_type_for_external_return, getpos
from vyper.compiler.output import build_source_map_output
from vyper.exceptions import VyperException  # for building source traces
from vyper.utils import abi_method_id, cached_property, keccak256

from boa.env import Env
from boa.object import VyperObject


# build a reverse map from the format we have in pc_pos_map to AST nodes
def ast_map_of(ast_node):
    ast_map = {}
    nodes = [ast_node] + ast_node.get_descendants(reverse=True)
    for node in nodes:
        ast_map[getpos(node)] = node
    return ast_map


class lrudict(dict):
    def __init__(self, n, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = n

    def __getitem__(self, k):
        val = super().__getitem__(k)
        del self[k]
        super().__setitem__(k, val)
        return val

    def __setitem__(self, k, val):
        if len(self) == self.n:
            del self[next(iter(self))]
        super().__setitem__(k, val)


import vyper.semantics.namespace as ns
import vyper.semantics.validation as vld


class VyperContract:
    _initialized = False
    def __init__(self, compiler_data, *args, env=None, override_address=None):
        global_ctx = compiler_data.global_ctx
        object.__setattr__(self, "global_ctx", global_ctx)
        self.compiler_data = compiler_data

        if env is None:
            env = Env.get_singleton()

        self.env = env
        if override_address is None:
            self.address = self.env.generate_address()
        else:
            self.address = override_address

        encoded_args = b""

        fns = {fn.name: fn for fn in global_ctx._function_defs}

        if "__init__" in fns:
            ctor = VyperFunction(fns.pop("__init__"), self)
            encoded_args = ctor._prepare_calldata(*args)
            encoded_args = encoded_args[4:]  # strip method_id

        self.bytecode = self.env.deploy_code(
            bytecode=self.compiler_data.bytecode + encoded_args, deploy_to=self.address
        )

        # add all functions from the interface to the contract
        for fn in fns.values():
            setattr(self, fn.name, VyperFunction(fn, self))

        for varname, varinfo in self.global_ctx._globals.items():
            if isinstance(varinfo.typ, vyper.MappingType):
                pass #setattr(self, varname, VyperMapping(self, varname, varinfo.typ))

        self._computation = None

        self._eval_cache = lrudict(0x1000)
        self._initialized = True

    # these were probably a bad idea
    #def __getattr__(self, attr):
    #    if self._initialized and attr in self.global_ctx._globals:
    #        return self.eval(f"self.{attr}")
    #    else:
    #        return super().__getattribute__(attr)

    #def __setattr__(self, attr, val):
    #    if self._initialized and attr in self.global_ctx._globals:
    #        self.eval(f"self.{attr} = {val}")
    #    else:
    #        super().__setattr__(attr, val)

    @cached_property
    def ast_map(self):
        return ast_map_of(self.compiler_data.vyper_module)

    @cached_property
    def source_map(self):
        return build_source_map_output(self.compiler_data)

    def find_source_of(self, code_stream, is_initcode=False):
        pc_map = self.source_map["pc_pos_map"]
        for pc in reversed(code_stream._trace):
            if pc in pc_map:
                return self.ast_map[pc_map[pc]]

        return None

    # run a bytecode fragment in the context of the contract,
    # maintaining PCs and CODESIZE semantics
    def _run_bytecode(self, fragment: bytes, calldata_bytes: bytes = b"") -> Any:
        bytecode = self.bytecode + fragment
        fake_codesize = len(self.bytecode)
        method_id = bytes.fromhex("ffffffff")
        computation = self.env.execute_code(
            to_address=self.address,
            bytecode=bytecode,
            data=method_id + calldata_bytes,
            fake_codesize=fake_codesize,
            start_pc=fake_codesize,
        )
        return computation

    def eval(self, stmt: str) -> Any:
        bytecode, typ = self.compile_stmt(stmt)

        c = self._run_bytecode(bytecode)

        self._computation = c  # for further inspection

        if c.is_error:
            raise BoaError(repr(c.error), self.find_source_of(c.code))

        if typ is None:
            return None

        return_typ = calculate_type_for_external_return(typ)
        ret = abi.decode_single(return_typ.abi_type.selector_name(), c.output)

        # unwrap the tuple if needed
        if not isinstance(typ, vyper.TupleType):
            (ret,) = ret

        return ret

    @cached_property
    def _ast_module(self):
        from vyper.ast.expansion import remove_unused_statements
        import vyper.ast as vy_ast

        ret = copy.deepcopy(self.compiler_data.vyper_module)
        vy_ast.folding.fold(ret)
        vld.validate_semantics(ret, self.compiler_data.interface_codes)

        # don't expand ast
        remove_unused_statements(ret)
        from vyper.semantics.validation.data_positions import set_data_positions

        set_data_positions(ret, storage_layout_overrides=None)
        return ret

    def compile_stmt(self, source_code: str) -> Any:
        # this method is super slow so we cache compilation results
        if source_code in self._eval_cache:
            return self._eval_cache[source_code]

        import vyper.ast as vy_ast
        from vyper.ast.utils import parse_to_ast
        from vyper.semantics.validation.utils import get_exact_type_from_node

        ast = parse_to_ast(source_code)
        vy_ast.folding.fold(ast)
        ast = ast.body[0]

        fake_module = self._ast_module
        from vyper.exceptions import StructureException

        if isinstance(ast, vy_ast.Expr):
            with ns.get_namespace().enter_scope():
                vld.add_module_namespace(
                    fake_module, self.compiler_data.interface_codes
                )
                typ = get_exact_type_from_node(ast.value)

            return_sig = f"-> {typ}"
            body = f"return {source_code}"
        else:
            typ = None
            return_sig = ""
            body = source_code

        # wrap code in function so that
        wrapper_code = f"""
@external
@payable
def __boa_debug__() {return_sig}:
    {body}
        """
        ast = parse_to_ast(wrapper_code, self.compiler_data.interface_codes)
        from vyper.semantics.validation import validate_semantics

        vy_ast.folding.fold(ast)

        from vyper.semantics.validation.data_positions import set_data_positions

        fake_module.body += ast.body

        with ns.get_namespace().enter_scope():
            vld.add_module_namespace(fake_module, self.compiler_data.interface_codes)
            vld.validate_functions(ast)

        set_data_positions(fake_module, storage_layout_overrides=None)

        ast = fake_module.body.pop(-1)

        sig = FunctionSignature.from_definition(ast, self.global_ctx)
        ast._metadata["signature"] = sig
        import vyper.codegen.function_definitions.common as vyper

        ir = vyper.generate_ir_for_function(
            ast,
            self.compiler_data.function_signatures,
            self.global_ctx,
            skip_nonpayable_check=False,
        )
        from vyper.codegen.ir_node import IRnode

        # force the selector check to always succeed
        ir = IRnode.from_list(
            ["with", "_calldata_method_id", abi_method_id(sig.base_signature), ir]
        )
        import vyper.ir.compile_ir as compile_ir

        assembly = compile_ir.compile_to_assembly(ir)

        # add padding so that jumpdests assembly correctly in final bytecode
        padding = len(self.bytecode)
        assembly = ["POP"] * padding + assembly
        bytecode, _ = compile_ir.assembly_to_evm(assembly)
        bytecode = bytecode[padding:]

        ret = bytecode, typ
        self._eval_cache[source_code] = ret
        return ret


# TODO probably remove me
class VyperMapping:
    def __init__(self, contract, name, typ, key_prefix=None):
        self.contract = contract
        self.name = name
        self.typ = typ
        self.key_prefix = key_prefix or []

    @property
    def _is_leaf(self):
        return not isinstance(self.typ.valuetype, vyper.MappingType)

    def _access(self, key):
        assert self._is_leaf
        # e.g. [a, b, c] => [a][b][c]
        subscript = "".join(f"[{k}]" for k in (self.key_prefix + [key]))
        return f"self.{self.name}{subscript}"

    def __getitem__(self, key):
        if self._is_leaf:
            return self.contract.eval(self._access(key))
        else:
            ks = self.key_prefix + [key]
            return VyperMapping(self.name, self.typ.valuetype, ks)

    def __setitem__(self, key, val):
        return self.contract.eval(f"{self._access(key)} = {val}")


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
        if not len(self.fn_signature.base_args) <= len(args) <= len(self.fn_signature.args):
            raise Exception(f"bad args to {self}")

        # align the kwargs with the signature
        # sig_kwargs = self.fn_signature.default_args[: len(kwargs)]

        total_non_base_args = len(kwargs) + len(args) - len(self.fn_signature.base_args)
        method_id, args_abi_type = self.args_abi_type(total_non_base_args)

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
        if not isinstance(self.fn_signature.return_type, vyper.TupleType):
            (ret,) = ret

        return VyperObject(ret, typ=self.fn_signature.return_type)

import decimal
import math
from boa.interpret.object import VyperObject

from vyper import ast as vy_ast
from vyper.codegen.types import (
    ArrayLike,
    BaseType,
    ByteArrayLike,
    ByteArrayType,
    DArrayType,
    EnumType,
    InterfaceType,
    MappingType,
    SArrayType,
    StringType,
    StructType,
    TupleType,
    is_base_type,
    is_bytes_m_type,
    is_numeric_type,
)
from vyper.codegen.types.convert import new_type_to_old_type
from vyper.exceptions import (
    CompilerPanic,
    EvmVersionException,
    StructureException,
    TypeCheckFailure,
    TypeMismatch,
    UnimplementedException,
)
from vyper.utils import (
    DECIMAL_DIVISOR,
    SizeLimits,
    bytes_to_int,
    is_checksum_encoded,
    string_to_bytes,
)

ENVIRONMENT_VARIABLES = {"block", "msg", "tx", "chain"}


class Expr:
    def __init__(self, node, context):
        self.expr = node
        self.context = context


    def interpret(self):
        fn = getattr(self, f"parse_{type(self.expr).__name__}", None)
        if fn is None:
            raise TypeCheckFailure(f"Invalid statement node: {type(self.expr).__name__}")

        ret = fn(self.expr)
        if ret is None:
            raise Exception(f"did not return a value, {self.expr}")
        return ret

    def parse_Int(self, expr):
        typ = new_type_to_old_type(expr._metadata.get("type"))
        return VyperObject(self.expr.n, typ)

    def parse_Decimal(self, expr):
        val = expr.n
        return VyperObject(val, typ=BaseType("decimal"))

    def parse_Hex(self, expr):
        hexstr = expr.value

        t = expr._metadata.get("type")

        n_bytes = (len(hexstr) - 2) // 2  # e.g. "0x1234" is 2 bytes

        typ = new_type_to_old_type(self.expr._metadata["type"])
        if is_base_type(typ, "address"):
            # sanity check typechecker did its job
            assert len(hexstr) == 42 and is_checksum_encoded(hexstr)
            typ = BaseType("address")
            return VyperObject(hexstr, typ)

        if is_bytes_m_type(typ):
            assert n_bytes == typ._bytes_info.m

            # bytes_m types are left padded with zeros
            val = int(hexstr, 16) << 8 * (32 - n_bytes)

            typ = BaseType(f"bytes{n_bytes}")
            return VyperObject(val, typ=typ)

    # String literals
    def parse_Str(self, expr):
        string = expr.s
        typ = StringType(len(string))
        return VyperObject(string, typ)

    # Byte literals
    def parse_Bytes(self, expr):
        bytez = expr.s
        typ = ByteArrayType(len(bytez))
        return VyperObject(bytez, typ)

    # True, False, None constants
    def parse_NameConstant(self, expr):
        return VyperObject(expr.value, BaseType("bool"))

    # Variable names
    def parse_Name(self, expr):

        name = expr.id

        t = self.context.get_var(name)
        if t is not None:
            return t

        if expr.id == "self":
            raise Exception("unimplemented")

        elif self.expr._metadata["type"].is_immutable:
            var = self.context.globals[self.expr.id]
            ofst = self.expr._metadata["type"].position.offset

            if self.context.sig.is_init_func:
                mutable = True
                location = IMMUTABLES
            else:
                mutable = False
                location = DATA

            return IRnode.from_list(
                ofst, typ=var.typ, location=location, annotation=self.expr.id, mutable=mutable
            )

    # x.y or x[5]
    def parse_Attribute(self, expr):
        typ = expr._metadata.get("type")
        if typ is not None:
            typ = new_type_to_old_type(typ)
        if isinstance(typ, EnumType):
            assert typ.name == expr.value.id
            # 0, 1, 2, .. 255
            enum_id = typ.members[expr.attr]
            value = 2 ** enum_id  # 0 => 0001, 1 => 0010, 2 => 0100, etc.
            return IRnode.from_list(value, typ=typ)

        # x.balance: balance of address x
        if expr.attr == "balance":
            addr = Expr.parse_value_expr(expr.value, self.context)
            if is_base_type(addr.typ, "address"):
                if (
                    isinstance(expr.value, vy_ast.Name)
                    and self.expr.value.id == "self"
                    and version_check(begin="istanbul")
                ):
                    seq = ["selfbalance"]
                else:
                    seq = ["balance", addr]
                return IRnode.from_list(seq, typ=BaseType("uint256"))
        # x.codesize: codesize of address x
        elif self.expr.attr == "codesize" or self.expr.attr == "is_contract":
            addr = Expr.parse_value_expr(self.expr.value, self.context)
            if is_base_type(addr.typ, "address"):
                if self.expr.attr == "codesize":
                    if self.expr.get("value.id") == "self":
                        eval_code = ["codesize"]
                    else:
                        eval_code = ["extcodesize", addr]
                    output_type = "uint256"
                else:
                    eval_code = ["gt", ["extcodesize", addr], 0]
                    output_type = "bool"
                return IRnode.from_list(eval_code, typ=BaseType(output_type))
        # x.codehash: keccak of address x
        elif self.expr.attr == "codehash":
            addr = Expr.parse_value_expr(self.expr.value, self.context)
            if not version_check(begin="constantinople"):
                raise EvmVersionException(
                    "address.codehash is unavailable prior to constantinople ruleset", self.expr
                )
            if is_base_type(addr.typ, "address"):
                return IRnode.from_list(["extcodehash", addr], typ=BaseType("bytes32"))
        # x.code: codecopy/extcodecopy of address x
        elif self.expr.attr == "code":
            addr = Expr.parse_value_expr(self.expr.value, self.context)
            if is_base_type(addr.typ, "address"):
                # These adhoc nodes will be replaced with a valid node in `Slice.build_IR`
                if addr.value == "address":  # for `self.code`
                    return IRnode.from_list(["~selfcode"], typ=ByteArrayType(0))
                return IRnode.from_list(["~extcode", addr], typ=ByteArrayType(0))
        # self.x: global attribute
        elif isinstance(self.expr.value, vy_ast.Name) and self.expr.value.id == "self":
            return getattr(self.context.contract, expr.attr)
        # Reserved keywords
        elif (
            isinstance(expr.value, vy_ast.Name) and expr.value.id in ENVIRONMENT_VARIABLES
        ):
            key = f"{self.expr.value.id}.{self.expr.attr}"
            if key == "msg.sender":
                return self.context.msg_ctx.msg["sender"]
            elif key == "msg.data":
                # This adhoc node will be replaced with a valid node in `Slice/Len.build_IR`
                return IRnode.from_list(["~calldata"], typ=ByteArrayType(0))
            elif key == "msg.value" and self.context.is_payable:
                return IRnode.from_list(["callvalue"], typ=BaseType("uint256"))
            elif key == "msg.gas":
                return IRnode.from_list(["gas"], typ="uint256")
            elif key == "block.difficulty":
                return IRnode.from_list(["difficulty"], typ="uint256")
            elif key == "block.timestamp":
                return IRnode.from_list(["timestamp"], typ=BaseType("uint256"))
            elif key == "block.coinbase":
                return IRnode.from_list(["coinbase"], typ="address")
            elif key == "block.number":
                return IRnode.from_list(["number"], typ="uint256")
            elif key == "block.gaslimit":
                return IRnode.from_list(["gaslimit"], typ="uint256")
            elif key == "block.basefee":
                return IRnode.from_list(["basefee"], typ="uint256")
            elif key == "block.prevhash":
                return IRnode.from_list(["blockhash", ["sub", "number", 1]], typ="bytes32")
            elif key == "tx.origin":
                return IRnode.from_list(["origin"], typ="address")
            elif key == "tx.gasprice":
                return IRnode.from_list(["gasprice"], typ="uint256")
            elif key == "chain.id":
                if not version_check(begin="istanbul"):
                    raise EvmVersionException(
                        "chain.id is unavailable prior to istanbul ruleset", self.expr
                    )
                return IRnode.from_list(["chainid"], typ="uint256")
        # Other variables
        else:
            sub = Expr(self.expr.value, self.context).ir_node
            # contract type
            if isinstance(sub.typ, InterfaceType):
                return sub
            if isinstance(sub.typ, StructType) and self.expr.attr in sub.typ.members:
                return get_element_ptr(sub, self.expr.attr)

    def parse_Subscript(self, expr):
        val = Expr(expr.value, self.context).interpret().value

        ix = Expr(expr.slice.value, self.context).interpret().value

        return val[ix]

    def parse_BinOp(self, expr):
        left = Expr(expr.left, self.context).interpret().value
        right = Expr(expr.right, self.context).interpret().value

        typ = new_type_to_old_type(expr._metadata["type"])

        return self.binop(typ, expr.op, left, right)

    @classmethod
    def binop(cls, typ, op, left, right):

        lo, hi = typ._int_info.bounds

        def finalize(val):
            if not (lo <= val <= hi):
                raise Exception(f"Out of bounds for {typ}: {val}")

            return VyperObject(val, typ=typ)

        if isinstance(op, vy_ast.BitAnd):
            return finalize(left & right)
        if isinstance(op, vy_ast.BitOr):
            return finalize(left | right)
        if isinstance(op, vy_ast.BitXor):
            return finalize(left ^ right)
        if isinstance(op, vy_ast.Add):
            return finalize(left + right)
        if isinstance(op, vy_ast.Sub):
            return finalize(left - right)
        if isinstance(op, vy_ast.Mult):
            return finalize(left * right)
        if isinstance(op, vy_ast.Div):
            return finalize(evm_div(left, right))
        if isinstance(op, vy_ast.Mod):
            return finalize(evm_mod(left, right))
        if isinstance(op, vy_ast.Pow):
            return finalize(left ** right)

    def build_in_comparator(self):
        left = Expr(self.expr.left, self.context).ir_node
        right = Expr(self.expr.right, self.context).ir_node

        # temporary kludge to block #2637 bug
        # TODO actually fix the bug
        if not isinstance(left.typ, BaseType):
            raise TypeMismatch(
                "`in` not allowed for arrays of non-base types, tracked in issue #2637", self.expr
            )

        if isinstance(self.expr.op, vy_ast.In):
            found, not_found = 1, 0
        elif isinstance(self.expr.op, vy_ast.NotIn):
            found, not_found = 0, 1
        else:
            return  # pragma: notest

        i = IRnode.from_list(self.context.fresh_varname("in_ix"), typ="uint256")

        found_ptr = self.context.new_internal_variable(BaseType("bool"))

        ret = ["seq"]

        left = unwrap_location(left)
        with left.cache_when_complex("needle") as (b1, left), right.cache_when_complex(
            "haystack"
        ) as (b2, right):
            if right.value == "multi":
                # Copy literal to memory to be compared.
                tmp_list = IRnode.from_list(
                    self.context.new_internal_variable(right.typ), typ=right.typ, location=MEMORY
                )
                ret.append(make_setter(tmp_list, right))

                right = tmp_list

            # location of i'th item from list
            ith_element_ptr = get_element_ptr(right, i, array_bounds_check=False)
            ith_element = unwrap_location(ith_element_ptr)

            if isinstance(right.typ, SArrayType):
                len_ = right.typ.count
            else:
                len_ = get_dyn_array_count(right)

            # Condition repeat loop has to break on.
            # TODO maybe put result on the stack
            loop_body = [
                "if",
                ["eq", left, ith_element],
                ["seq", ["mstore", found_ptr, found], "break"],  # store true.
            ]
            loop = ["repeat", i, 0, len_, right.typ.count, loop_body]

            ret.append(["seq", ["mstore", found_ptr, not_found], loop, ["mload", found_ptr]])

            return IRnode.from_list(b1.resolve(b2.resolve(ret)), typ="bool")


    def parse_Compare(self, expr):
        left = Expr(expr.left, self.context).interpret().value
        right = Expr(expr.right, self.context).interpret().value

        def finalize(val):
            return VyperObject(bool(val), typ=BaseType("bool"))

        rtyp = new_type_to_old_type(expr.right._metadata["type"])

        if isinstance(rtyp, ArrayLike):
            if isinstance(expr.op, vy_ast.In):
                return finalize(left in right)
            if isinstance(expr.op, vy_ast.NotIn):
                return finalize(left not in right)
            raise Exception("unreachable")

        if isinstance(rtyp, EnumType):
            if isinstance(expr.op, vy_ast.In):
                return finalize((left & right) == 0)
            if isinstance(self.expr.op, vy_ast.NotIn):
                return finalize((left & right) != 0)
            raise Exception("unreachable")

        if isinstance(expr.op, vy_ast.Gt):
            return finalize(left > right)
        if isinstance(expr.op, vy_ast.GtE):
            return finalize(left >= right)
        if isinstance(expr.op, vy_ast.LtE):
            return finalize(left <= right)
        if isinstance(expr.op, vy_ast.Lt):
            return finalize(left < right)
        if isinstance(expr.op, vy_ast.Eq):
            return finalize(left == right)
        if isinstance(self.expr.op, vy_ast.NotEq):
            return finalize(left != right)

        raise Exception("unreachable")

        # Compare (limited to 32) byte arrays.
        if isinstance(left.typ, ByteArrayLike) and isinstance(right.typ, ByteArrayLike):
            left = Expr(self.expr.left, self.context).ir_node
            right = Expr(self.expr.right, self.context).ir_node

            left_keccak = keccak256_helper(self.expr, left, self.context)
            right_keccak = keccak256_helper(self.expr, right, self.context)

            if op not in ("eq", "ne"):
                return  # raises
            else:
                # use hash even for Bytes[N<=32], because there could be dirty
                # bytes past the bytes data.
                return IRnode.from_list([op, left_keccak, right_keccak], typ="bool")

        # Compare other types.
        elif is_numeric_type(left.typ) and is_numeric_type(right.typ):
            if left.typ.typ == right.typ.typ == "uint256":
                # signed comparison ops work for any integer
                # type BESIDES uint256
                op = self._signed_to_unsigned_comparision_op(op)

        elif isinstance(left.typ, BaseType) and isinstance(right.typ, BaseType):
            if op not in ("eq", "ne"):
                return
        else:
            # kludge to block behavior in #2638
            # TODO actually implement equality for complex types
            raise TypeMismatch(
                f"operation not yet supported for {left.typ}, {right.typ}, see issue #2638",
                self.expr.op,
            )

        return IRnode.from_list([op, left, right], typ="bool")

    def parse_BoolOp(self, expr):
        for arg in self.expr.values:
            t = Expr(arg, self.context).interpret().value
            if isinstance(expr.op, vy_ast.Or) and t is True:
                break
            if isinstance(expr.op, vy_ast.And) and t is False:
                break

        return VyperObject(t, typ=BaseType("bool"))

    # Unary operations (only "not" supported)
    def parse_UnaryOp(self):
        operand = Expr.parse_value_expr(self.expr.operand, self.context)
        if isinstance(self.expr.op, vy_ast.Not):
            if isinstance(operand.typ, BaseType) and operand.typ.typ == "bool":
                return IRnode.from_list(["iszero", operand], typ="bool")

        if isinstance(self.expr.op, vy_ast.Invert):
            if isinstance(operand.typ, EnumType):
                n_members = len(operand.typ.members)
                # use (xor 0b11..1 operand) to flip all the bits in
                # `operand`. `mask` could be a very large constant and
                # hurt codesize, but most user enums will likely have few
                # enough members that the mask will not be large.
                mask = (2 ** n_members) - 1
                return IRnode.from_list(["xor", mask, operand], typ=operand.typ)

            if is_base_type(operand.typ, "uint256"):
                return IRnode.from_list(["not", operand], typ=operand.typ)

            # block `~` for all other integer types, since reasoning
            # about dirty bits is not entirely trivial. maybe revisit
            # this at a later date.
            raise UnimplementedException(f"~ is not supported for {operand.typ}", self.expr)

        if isinstance(self.expr.op, vy_ast.USub) and is_numeric_type(operand.typ):
            assert operand.typ._num_info.is_signed
            # Clamp on minimum signed integer value as we cannot negate that
            # value (all other integer values are fine)
            min_int_val, _ = operand.typ._num_info.bounds
            return IRnode.from_list(["sub", 0, clamp("sgt", operand, min_int_val)], typ=operand.typ)

    def _is_valid_interface_assign(self):
        if self.expr.args and len(self.expr.args) == 1:
            arg_ir = Expr(self.expr.args[0], self.context).ir_node
            if arg_ir.typ == BaseType("address"):
                return True, arg_ir
        return False, None

    # Function calls
    def parse_Call(self, expr):
        # TODO check out this inline import
        from vyper.builtin_functions import DISPATCH_TABLE

        args = [Expr(arg, self.context).interpret() for arg in expr.args]

        # TODO just use Expr(func, self.context).interpret().eval(args)

        if isinstance(self.expr.func, vy_ast.Name):
            function_name = self.expr.func.id

            if function_name in DISPATCH_TABLE:
                return DISPATCH_TABLE[function_name].eval(self.context, *args)

            # Struct constructors do not need `self` prefix.
            elif function_name in self.context.structs:
                args = self.expr.args
                if len(args) == 1 and isinstance(args[0], vy_ast.Dict):
                    return Expr.struct_literals(args[0], function_name, self.context)

            # Interface assignment. Bar(<address>).
            elif function_name in self.context.sigs:
                ret, arg_ir = self._is_valid_interface_assign()
                if ret is True:
                    arg_ir.typ = InterfaceType(function_name)  # Cast to Correct interface type.
                    return arg_ir

        elif isinstance(self.expr.func, vy_ast.Attribute) and self.expr.func.attr == "pop":
            # TODO consider moving this to builtins
            darray = Expr(self.expr.func.value, self.context).ir_node
            assert len(self.expr.args) == 0
            assert isinstance(darray.typ, DArrayType)
            return pop_dyn_array(darray, return_popped_item=True)

        elif (
            isinstance(expr.func, vy_ast.Attribute)
            and isinstance(expr.func.value, vy_ast.Name)
            and expr.func.value.id == "self"
        ):
            # self.foo()
            funcname = expr.func.attr
            args = [arg.value for arg in args]
            return getattr(self.context.contract, funcname).__call__(*args)
        else:
            return external_call.ir_for_external_call(self.expr, self.context)

    def parse_List(self):
        typ = new_type_to_old_type(self.expr._metadata["type"])
        if len(self.expr.elements) == 0:
            return IRnode.from_list("~empty", typ=typ)

        multi_ir = [Expr(x, self.context).ir_node for x in self.expr.elements]

        return IRnode.from_list(["multi"] + multi_ir, typ=typ)

    def parse_Tuple(self):
        tuple_elements = [Expr(x, self.context).ir_node for x in self.expr.elements]
        typ = TupleType([x.typ for x in tuple_elements], is_literal=True)
        multi_ir = IRnode.from_list(["multi"] + tuple_elements, typ=typ)
        return multi_ir

    @staticmethod
    def struct_literals(expr, name, context):
        member_subs = {}
        member_typs = {}
        for key, value in zip(expr.keys, expr.values):
            if not isinstance(key, vy_ast.Name):
                return
            if key.id in member_subs:
                return
            sub = Expr(value, context).ir_node
            member_subs[key.id] = sub
            member_typs[key.id] = sub.typ

        # TODO: get struct type from context.global_ctx.parse_type(name)
        return IRnode.from_list(
            ["multi"] + [member_subs[key] for key in member_subs.keys()],
            typ=StructType(member_typs, name, is_literal=True),
        )

    # Parse an expression that represents a pointer to memory/calldata or storage.
    @classmethod
    def parse_pointer_expr(cls, expr, context):
        o = cls(expr, context).ir_node
        if not o.location:
            raise StructureException("Looking for a variable location, instead got a value", expr)
        return o

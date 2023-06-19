import contextlib
import inspect
import textwrap
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Optional
from pathlib import PurePath

import vyper.ir.optimizer
from eth.exceptions import Revert
from vyper.evm.opcodes import OPCODES
from vyper.utils import unsigned_to_signed, mkalphanum


def debug(*args, **kwargs):
    print(*args, **kwargs)


def ceil32(x):
    return (x + 31) & ~31


@dataclass
class _Line:
    indentation_level: int
    line: str

    def show(self, indenter=" "):
        return indenter * self.indentation_level + self.line


@dataclass
class PythonBuilder:
    cur_indentation_level: int = 0
    lines: list[_Line] = field(default_factory=list)

    def extend(self, source_code):
        source_code = textwrap.dedent(source_code)
        for line in source_code.splitlines():
            self.append(line)

    def append(self, source_code):
        self.lines.append(_Line(self.cur_indentation_level, source_code))

    def get_output(self):
        return "\n".join(line.show() for line in self.lines)

    def get_code(self, filename):
        return compile(self.get_output())

    @contextlib.contextmanager
    def block(self, entry):
        self.append(entry + ":")
        self.cur_indentation_level += 4
        yield
        self.cur_indentation_level -= 4


@dataclass
class FrameInfo:
    current_slot: int = 0  # basically the de bruijn index
    slots: dict[str, int] = field(default_factory=lambda: {})


_global_id = 0


@dataclass
class CompileContext:
    contract_path: Optional[str] = ""
    uuid: str = field(init=False)
    labels: dict[str, "IRExecutor"] = field(default_factory=dict)
    frames: list[FrameInfo] = field(default_factory=lambda: [FrameInfo()])
    builder: PythonBuilder = field(default_factory=PythonBuilder)

    def __post_init__(self):
        # use a global bc the generated functions need to be unique
        global _global_id
        self.uuid = str(_global_id)
        _global_id += 1


    @property
    def local_vars(self):
        return self.frames[-1].slots

    @cached_property
    def contract_name(self):
        return mkalphanum(PurePath(self.contract_path).name)

    def translate_label(self, label):
        return f"{label}_{self.contract_name}_{self.uuid}"


    @contextlib.contextmanager
    def allocate_local_frame(self):
        frame = FrameInfo()
        self.frames.append(frame)
        yield  # frame
        self.frames.pop()

    @contextlib.contextmanager
    def variables(self, vars_list):
        # allocate variables in vars_list, assigning them each
        # a new slot.
        shadowed = {}
        frame = self.frames[-1]
        for varname in vars_list:
            shadowed[varname] = frame.slots.get(varname)
            frame.slots[varname] = frame.current_slot
            frame.current_slot += 1

        yield

        for varname in vars_list:
            frame.current_slot -= 1
            if shadowed[varname] is None:
                del frame.slots[varname]
            else:
                frame.slots[varname] = shadowed[varname]


StackItem = int | bytes


mapper = {int: "_to_int", bytes: "_to_bytes", StackItem: ""}


class IRExecutor:
    __slots__ = ("args", "compile_ctx", "exec")

    _out_type: Optional[StackItem] = None

    def __init__(self, compile_ctx, *args):
        self.args = args
        self.compile_ctx = compile_ctx
        self.py_bytecode = None

    def get_output(self):
        return self.builder.get_output()

    @cached_property
    def name(self):
        return self._name

    def _compile_args(self, argnames):
        assert len(self.args) == len(argnames) == len(self._sig), (self.args, argnames, self._sig)
        for out, arg, typ in reversed(list(zip(argnames, self.args, self._sig))):
            arg.compile(out=out, out_typ=typ)

    @property
    def builder(self):
        return self.compile_ctx.builder

    def analyze(self):
        self.args = [arg.analyze() for arg in self.args]
        return self

    def compile(self, out=None, out_typ=None):
        # do a bit of metaprogramming to infer how to compile the args
        if hasattr(self, "_argnames"):
            argnames = self._argnames
        else:
            argnames = inspect.getargs(self._compile.__code__).args
            assert argnames[0] == "self"
            argnames = argnames[1:]

        self._compile_args(argnames)

        res = self._compile(*argnames)

        if res is None:
            assert out is None, (type(self), self, out, argnames)
            return

        #print("ENTER", type(self), self, out, argnames, res)
        res_typ, res = res

        if out is not None:
            if res_typ != out_typ:
                res = f"{mapper[out_typ]}({res})"
            self.builder.append(f"{out} = {res}")
        else:
            self.builder.append(res)

    def _compile(self, context):
        raise RuntimeError("must be overridden in subclass!")

    def compile_main(self, contract_path=""):
        self.builder.extend("import vyper.utils\nimport _operator")

        main_name = self.compile_ctx.translate_label("main")
        with self.builder.block(f"def {main_name}(CTX)"):
            self.compile()

        for func in self.compile_ctx.labels.values():
            self.builder.extend("\n\n")
            func.compile_func()

        py_bytecode = compile(self.builder.get_output(), contract_path, "exec")
        exec(py_bytecode, globals())
        self.exec = globals()[main_name]


@dataclass
class IntExecutor(IRExecutor):
    compile_ctx: CompileContext
    _int_value: int

    def __post_init__(self):
        assert 0 <= self._int_value < 2**256
        self.args = self._sig = ()

    def __repr__(self):
        return hex(self._int_value)

    def analyze(self):
        return self

    def _compile(self):
        return int, repr(self)


@dataclass
class StringExecutor(IRExecutor):
    compile_ctx: CompileContext
    _str_value: str

    def __post_init__(self):
        self.args = self._sig = ()

    def __repr__(self):
        return repr(self._str_value)

    def analyze(self):
        slot = self.compile_ctx.local_vars[self._str_value]
        return VariableExecutor(self.compile_ctx, self._str_value, slot)


@dataclass
class VariableExecutor(IRExecutor):
    compile_ctx: CompileContext
    varname: str
    var_slot: int

    def __post_init__(self):
        self.args = self._sig = ()

    def __repr__(self):
        return f"var({self.varname})"
      
    @cached_property
    def out_name(self):
        slot = self.var_slot
        ret = f"__user_{self.varname}"
        if slot > 0:
            ret += f"_{slot}"
        return ret

    def _compile(self):
        return StackItem, self.out_name # XXX: figure out type

@dataclass
class OpcodeInfo:
    # model of an opcode from vyper.evm.opcodes
    mnemonic: str
    opcode: int  # opcode number ex. 0x01 for ADD
    consumes: int  # number of stack items this consumes
    produces: int  # number of stack items this produces, must be 0 or 1
    _gas_estimate: int  # in vyper.evm.opcodes but probably not useful for us

    def __post_init__(self):
        assert 0 <= self.opcode < 256
        assert self.produces in (0, 1)

    @classmethod
    def from_opcode_info(cls, mnemonic, opcode_info):
        # info from vyper.evm.opcodes
        opcode, consumes, produces, gas_estimate = opcode_info
        return cls(mnemonic, opcode, consumes, produces, gas_estimate)


# an executor for evm opcodes which dispatches into py-evm
class OpcodeIRExecutor(IRExecutor):
    def __init__(self, name, opcode_info, *args):
        self.opcode_info: OpcodeInfo = opcode_info

        # to differentiate from implemented codes
        self._name = "__" + name + "__"

        super().__init__(*args)

    @cached_property
    def _sig(self):
        return tuple(StackItem for _ in range(self.opcode_info.consumes))

    @cached_property
    def _argnames(self):
        def mkargname(i):
            return f"__{self.opcode_info.mnemonic.lower()}_arg{i}"

        return tuple(mkargname(i) for i in range(self.opcode_info.consumes))

    def _compile(self, *args):
        opcode = hex(self.opcode_info.opcode)
        for arg in reversed(args):
            # TODO figure out the type to avoid calling _to_int
            self.builder.append(f"CTX.computation.stack_push_int(_to_int({arg}))")

        self.builder.extend(
            f"""
        # {self._name}
        CTX.computation.opcodes[{opcode}].__call__(CTX.computation)
        """
        )
        if self.opcode_info.produces:
            return StackItem, "CTX.computation.stack_pop1_any()"


_executors = {}


# decorator to register an executor class in the _executors dict.
def executor(cls):
    _executors[cls._name] = cls
    return cls


def _to_int(stack_item: StackItem) -> int:
    if isinstance(stack_item, int):
        return stack_item
    return int.from_bytes(stack_item, "big")


def _to_bytes(stack_item: StackItem) -> bytes:
    if isinstance(stack_item, bytes):
        return stack_item
    return stack_item.to_bytes(32, "big")


def _wrap256(x):
    return x % 2**256


def _as_signed(x):
    return unsigned_to_signed(x, 256, strict=True)


class UnsignedBinopExecutor(IRExecutor):
    __slots__ = ("_name", "_op")
    _sig = int, int
    _out_type = int

    @cached_property
    def funcname(self):
        return self._op.__module__ + "." + self._op.__name__

    def _compile(self, x, y):
        return int, f"_wrap256({self.funcname}({x}, {y}))"


class SignedBinopExecutor(UnsignedBinopExecutor):
    def _compile(self, x, y):
        self.builder.extend(
            f"""
        x = _as_signed({x}, 256, strict=True))
        y = _as_signed({y}, 256, strict=True))
        """
        )
        return int, f"_wrap256({self._funcname}(x, y))"


# for binops, just use routines from vyper optimizer
for opname, (op, _, unsigned) in vyper.ir.optimizer.arith.items():
    base = UnsignedBinopExecutor if unsigned else SignedBinopExecutor
    nickname = opname.capitalize()
    _executors[opname] = type(nickname, (base,), {"_op": op, "_name": opname})


@executor
class MLoad(IRExecutor):
    _name = "mload"
    _sig = (int,)

    def _compile(self, ptr):
        self.builder.append(f"CTX.computation._memory.extend({ptr}, 32)")
        return int, f"CTX.computation._memory.read_word({ptr})"


@executor
class MStore(IRExecutor):
    _name = "mstore"
    _sig = (int, int)

    def _compile(self, val, ptr):
        self.builder.extend(
            f"""
        CTX.computation._memory.extend({ptr}, 32)
        CTX.computation._memory.write_word({ptr}, {val})
        """
        )


@executor
class Ceil32(IRExecutor):
    _name = "ceil32"
    _sig = (int,)

    def _compile(self, x):
        return int, f"({x} + 31) & 31"

@executor
class IsZero(IRExecutor):
    _name = "iszero"
    _sig = (int,)

    def _compile(self, x):
        return int, f"{x} == 0"



# @executor
class DLoad(IRExecutor):
    _name = "dload"
    _sig = (int,)

    def _impl(self, context, ptr):
        raise RuntimeError("unimplemented")


# @executor
class DLoadBytes(IRExecutor):
    _name = "dloadbytes"

    def _impl(self, context, dst, src, size):
        raise RuntimeError("unimplemented")


@executor
class Pass(IRExecutor):
    _name = "pass"
    _sig = ()
    _argnames = ()

    def _compile(self):
        self.builder.append("pass")


@executor
class Seq(IRExecutor):
    _name = "seq"

    def compile(self, out=None, out_typ=None):
        for i, arg in enumerate(self.args):
            if i + 1 < len(self.args):
                # don't accidentally assign
                arg.compile(out=None)
            else:
                return arg.compile(out=out, out_typ=out_typ)
        else:
            raise RuntimeError("loop should have broken")


@executor
class Repeat(IRExecutor):
    _name = "repeat"

    def compile(self, out=None):
        i_var, start, rounds, rounds_bound, body = self.args

        start.compile("start", int)
        rounds.compile("rounds", int)
        rounds_bound.compile("rounds_bound", int)
        end = "start + rounds"

        self.builder.append(f"assert rounds <= rounds_bound")
        with self.builder.block(f"for {i_var.out_name} in range(start, {end})"):
            body.compile()

    def analyze(self):
        i_name, start, rounds, rounds_bound, body = self.args

        # analyze start and rounds before shadowing.
        start = start.analyze()
        rounds = rounds.analyze()

        with self.compile_ctx.variables([i_name._str_value]):
            i_var = i_name.analyze()
            body = body.analyze()
        self.args = i_var, start, rounds, rounds_bound, body
        return self


@executor
class If(IRExecutor):
    _name = "if"

    # override `compile()` so we can get the correct lazy behavior
    def compile(self, out=None, out_typ=None):
        orelse = None
        if len(self.args) == 3:
            test, body, orelse = self.args
        else:
            test, body = self.args

        test.compile("test", out_typ=int)

        with self.builder.block("if bool(test)"):
            body.compile(out, out_typ)

        if orelse:
            with self.builder.block("else"):
                orelse.compile(out, out_typ)


@executor
class Assert(IRExecutor):
    _name = "assert"
    _sig = (int,)

    def _compile(self, test):
        _ = Revert  # linter does not know we are using `Revert`.
        self.builder.extend(
            """
        if not bool(test):
            CTX.computation.output = b""
            raise Revert(b"")
        """
        )


@executor
class VarList(IRExecutor):
    _name = "var_list"


@executor
class Goto(IRExecutor):
    _name = "goto"

    def analyze(self):
        self.label = self.args[0]._str_value
        if self.label.startswith("_sym_"):
            self.label = self.label[len("_sym_"):]

        for arg in self.args[1:]:
            arg = arg.analyze()

        self.args = self.args[1:]

        return self

    @cached_property
    def _argnames(self):
        return self.compile_ctx.labels[self.label].param_names

    @cached_property
    def _sig(self):
        return tuple(StackItem for _ in self._argnames)

    def _compile(self, *args):
        label = self.label

        if label == "returnpc":
            # i.e. exitsub
            assert len(args) == 0
            self.builder.append("return")
            return

        argnames = self._argnames
        assert len(argnames) == len(self.args)

        args_str = ", ".join(["CTX"] + argnames)
        # XXX: figure out type
        return StackItem, f"{label}({args_str})"


@executor
class ExitTo(Goto):
    # exit_to and goto have pretty much the same semantics as far as we
    # are concerned here.
    _name = "exit_to"


@executor
class Label(IRExecutor):
    _name = "label"

    def __init__(self, compile_ctx, *args):
        self.compile_ctx = compile_ctx

        name, var_list, body = args

        self.var_list = var_list.args
        self.body = body
        self.labelname = name._str_value

        if name._str_value in compile_ctx.labels:
            raise ValueError("duplicated label: {name._str_value}")
        compile_ctx.labels[name._str_value] = self

    @cached_property
    def param_names(self):
        return [param._str_value for param in self.var_list]

    def analyze(self):
        with self.compile_ctx.allocate_local_frame():
            with self.compile_ctx.variables(self.param_names):
                self.body = self.body.analyze()

        return self

    def compile(self, **kwargs):
        pass

    def compile_func(self):
        print(self.var_list)
        params_str = ", ".join(["CTX"] + self.param_names)
        with self.builder.block(f"def {self.labelname}({params_str})"):
            self.body.compile()


@executor
class With(IRExecutor):
    _name = "with"

    # variable names can be shadowed, so we need to do a bit of
    # analysis to find unshadowed names
    def analyze(self):
        varname = self.args[0]._str_value
        val = self.args[1].analyze()  # analyze before shadowing

        with self.compile_ctx.variables([varname]):
            variable = self.args[0].analyze()
            body = self.args[2].analyze()

            self.args = (variable, val, body)

        return self

    def compile(self, out=None, out_typ=None):
        variable, val, body = self.args
        # TODO: infer val typ
        val.compile(out=variable.out_name, out_typ=StackItem)
        return body.compile(out=out, out_typ=out_typ)


def executor_from_ir(ir_node, contract_path = "") -> Any:
    ret = _executor_from_ir(ir_node, CompileContext(contract_path))

    ret = ret.analyze()
    ret.compile_main()
    return ret


def _executor_from_ir(ir_node, compile_ctx) -> Any:
    instr = ir_node.value
    if isinstance(instr, int):
        return IntExecutor(compile_ctx, instr)

    args = [_executor_from_ir(arg, compile_ctx) for arg in ir_node.args]

    if instr in _executors:
        return _executors[instr](compile_ctx, *args)

    if (mnemonic := instr.upper()) in OPCODES:
        opcode_info = OpcodeInfo.from_opcode_info(mnemonic, OPCODES[mnemonic])
        return OpcodeIRExecutor(instr, opcode_info, compile_ctx, *args)

    assert len(ir_node.args) == 0, ir_node
    assert isinstance(ir_node.value, str)
    return StringExecutor(compile_ctx, ir_node.value)

import contextlib
import inspect
import textwrap
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import PurePath
from typing import Any, Optional

import vyper.ir.optimizer
from eth.exceptions import Revert
from vyper.compiler.phases import CompilerData
from vyper.evm.opcodes import OPCODES
from vyper.utils import mkalphanum, unsigned_to_signed

from boa.vm.fast_mem import FastMem
from boa.vm.utils import to_bytes, to_int


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
    types: dict[str, type] = field(default_factory=lambda: {})


_global_id = 0


@dataclass
class CompileContext:
    # include CompilerData - we need this to get immutable section size
    vyper_compiler_data: CompilerData
    uuid: str = field(init=False)
    labels: dict[str, "IRExecutor"] = field(default_factory=dict)
    unique_symbols: set[str] = field(default_factory=set)
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
        return mkalphanum(PurePath(self.vyper_compiler_data.contract_name).name)

    def translate_label(self, label):
        return f"{label}_{self.contract_name}_{self.uuid}"

    def add_unique_symbol(self, symbol):
        if symbol in self.unique_symbols:
            raise ValueError(
                "duplicated symbol {symbol}, this is likely a bug in vyper!"
            )
        self.unique_symbols.add(symbol)

    def add_label(self, labelname, executor):
        if labelname in self.labels:
            raise ValueError("duplicated label: {labelname}")
        self.labels[labelname] = executor

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


mapper = {int: "to_int", bytes: "to_bytes", StackItem: ""}


class ExecutionContext:
    __slots__ = "computation"

    def __init__(self, computation):
        self.computation = computation


class IRExecutor:
    __slots__ = ("args", "compile_ctx", "_exec", "ir_node")

    # the type produced when executing this node
    _type: Optional[type] = None  # | int | bytes

    def __init__(self, ir_node, compile_ctx, *args):
        self.ir_node = ir_node
        self.args = args
        self.compile_ctx = compile_ctx

    @cached_property
    def name(self):
        return self._name

    def _compile_args(self, argnames):
        assert len(self.args) == len(argnames) == len(self._sig), (
            type(self),
            self.args,
            argnames,
            self._sig,
            self.ir_node,
        )
        for out, arg, typ in reversed(list(zip(argnames, self.args, self._sig))):
            arg.compile(out=out, out_typ=typ)

    @cached_property
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

        if hasattr(self, "_name"):
            self.builder.append(f"# {self.name}")

        res = self._compile(*argnames)

        if res is None:
            assert out is None, (type(self), self, out, argnames)
            return

        if out is not None:
            # squash F401 lint complaint about import
            _ = to_int, to_bytes
            if self._type != out_typ:
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
            self.builder.append("VM = CTX.computation")
            self.compile()

        for func in self.compile_ctx.labels.values():
            self.builder.extend("\n\n")
            func.compile_func()

        py_bytecode = compile(self.builder.get_output(), contract_path, "exec")
        exec(py_bytecode, globals())

        self._exec = globals()[main_name]

    def exec(self, computation):
        computation._memory = FastMem()
        execution_ctx = ExecutionContext(computation)
        self._exec(execution_ctx)


@dataclass
class IntExecutor(IRExecutor):
    compile_ctx: CompileContext
    _int_value: int
    _type: type = int

    def __post_init__(self):
        assert 0 <= self._int_value < 2**256
        self.args = self._sig = ()

    def __repr__(self):
        return hex(self._int_value)

    def analyze(self):
        return self

    def _compile(self):
        return repr(self)


@dataclass
class StringExecutor(IRExecutor):
    compile_ctx: CompileContext
    _str_value: str

    @property
    def _type(self):
        raise RuntimeError("should have been analyzed!")

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

    # optimization assumption: most variables that
    # will be hotspots need to be ints.
    _type: type = int

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

    def analyze(self):
        raise RuntimeError("Should not appear during analysis!")

    def _compile(self):
        return self.out_name


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

    @classmethod
    def from_mnemonic(cls, mnemonic):
        mnemonic = mnemonic.upper()
        return cls.from_opcode_info(mnemonic, OPCODES[mnemonic])


# an executor for evm opcodes which dispatches into py-evm
class OpcodeIRExecutor(IRExecutor):
    _type: type = StackItem

    def __init__(self, name, opcode_info, *args):
        self.opcode_info: OpcodeInfo = opcode_info

        # to differentiate from implemented codes
        self._name = "__" + name + "__"

        super().__init__(*args)

    def __repr__(self):
        args = ",".join(repr(arg) for arg in self.args)
        return f"{self.name}({args})"

    @cached_property
    def _sig(self):
        # TODO figure out the type to avoid calling to_int
        return tuple(int for _ in range(self.opcode_info.consumes))

    @cached_property
    def _argnames(self):
        def mkargname(i):
            return f"__{self.opcode_info.mnemonic.lower()}_arg{i}"

        return tuple(mkargname(i) for i in range(self.opcode_info.consumes))

    def _compile(self, *args):
        for arg in reversed(args):
            self.builder.append(f"VM.stack_push_int({arg})")

        opcode = hex(self.opcode_info.opcode)
        self.builder.append(f"VM.opcodes[{opcode}].__call__(CTX.computation)")
        if self.opcode_info.produces:
            return "VM.stack_pop1_any()"


_executors = {}


# decorator to register an executor class in the _executors dict.
def executor(cls):
    _executors[cls._name] = cls
    return cls


def _wrap256(x):
    return x % 2**256


def _as_signed(x):
    return unsigned_to_signed(x, 256, strict=True)


class UnsignedBinopExecutor(IRExecutor):
    __slots__ = ("_name", "_op")
    _sig = int, int
    _type: type = int

    @cached_property
    def funcname(self):
        return self._op.__module__ + "." + self._op.__name__

    def _compile(self, x, y):
        return f"_wrap256({self.funcname}({x}, {y}))"


class SignedBinopExecutor(UnsignedBinopExecutor):
    def _compile(self, x, y):
        self.builder.extend(
            f"""
        x = _as_signed({x}, 256, strict=True))
        y = _as_signed({y}, 256, strict=True))
        """
        )
        return f"_wrap256({self._funcname}(x, y))"


# for binops, just use routines from vyper optimizer
for opname, (op, _, unsigned) in vyper.ir.optimizer.arith.items():
    base = UnsignedBinopExecutor if unsigned else SignedBinopExecutor
    nickname = opname.capitalize()
    _executors[opname] = type(nickname, (base,), {"_op": op, "_name": opname})


@executor
class MLoad(IRExecutor):
    _name = "mload"
    _sig = (int,)
    _type: type = int

    def _compile(self, ptr):
        self.builder.append(f"VM._memory.extend({ptr}, 32)")
        return f"VM._memory.read_word({ptr})"


@executor
class MStore(IRExecutor):
    _name = "mstore"
    _sig = (int, int)

    def _compile(self, ptr, val):
        self.builder.extend(
            f"""
        VM._memory.extend({ptr}, 32)
        VM._memory.write_word({ptr}, {val})
        """
        )


class _CodeLoader(IRExecutor):
    @cached_property
    def runtime_code_size(self):
        return self.compiler_data.global_ctx.immutable_section_bytes


@executor
class DLoad(_CodeLoader):
    _name = "dload"
    _sig = (int,)
    _type: type = bytes

    def _compile(self, ptr):
        self.builder.extend(
            f"""
        code_start_position = {ptr} + {self.runtime_code_size}

        with VM.code.seek(code_start_position):
            ret = VM.code.read(32)

        return ret.ljust(size, b"\x00")
        """
        )


@executor
class DLoadBytes(_CodeLoader):
    _name = "dloadbytes"
    _sig = (int, int, int)

    def _compile(self, dst, src, size):
        # adapted from py-evm codecopy, but without gas metering and
        # mess with the start position
        self.builder.extend(
            f"""
        code_start_position = {src} + {self.runtime_code_size}
        VM.extend_memory({dst}, {size})

        with VM.code.seek(code_start_position):
            code_bytes = VM.code.read({size})

        padded_code_bytes = code_bytes.ljust(size, b"\x00")

        VM.memory_write({dst}, {size}, padded_code_bytes)
        """
        )


# we call into py-evm for sha3_32 and sha3_64 to allow tracing to still work
class _Sha3_N(IRExecutor):
    _type: type = bytes

    @cached_property
    def _argnames(self):
        return tuple(f"{self.name}.arg{i}" for i in range(len(self._sig)))

    def _compile(self, *args):
        assert self.N > 0 and self.N % 32 == 0
        opcode_info = OpcodeInfo.from_mnemonic("SHA3")
        self.builder.append(f"VM.extend_memory(0, {self.N})")
        for i, val in enumerate(args):
            self.builder.append(f"VM.memory_write({i*32}, 32, {val})")

        sha3 = hex(opcode_info.opcode)
        self.builder.extend(
            f"""
        VM.stack_push_int({self.N})
        VM.stack_push_int(0)
        VM.opcodes[{sha3}].__call__(VM)
        """
        )
        return "VM.stack_pop1_any()"


@executor
class Sha3_64(_Sha3_N):
    _name = "sha3_64"
    _sig = (bytes, bytes)
    _argnames = ("sha3_64_arg0", "sha3_64_arg1")
    N = 64


@executor
class Sha3_32(_Sha3_N):
    _name = "sha3_32"
    _sig = (bytes,)
    _argnames = ("sha3_32_arg0",)
    N = 32


@executor
class Ceil32(IRExecutor):
    _name = "ceil32"
    _sig = (int,)
    _type: type = int

    def _compile(self, x):
        return f"({x} + 31) & 31"


@executor
class IsZero(IRExecutor):
    _name = "iszero"
    _sig = (int,)
    _type: type = int

    def _compile(self, x):
        return f"({x} == 0)"


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

        start.compile("start", out_typ=int)
        rounds.compile("rounds", out_typ=int)
        rounds_bound.compile("rounds_bound", out_typ=int)
        end = "start + rounds"

        self.builder.append("assert rounds <= rounds_bound")
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
            VM.output = b""
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
        # exit_to labels weird, fixed in GH vyper#3488
        if self.label.startswith("_sym_"):
            self.label = self.label[len("_sym_") :]

        # just get the parameters, leaving the label in self.args
        # messes with downstream machinery which tries to analyze the label.
        runtime_args = []
        for arg in self.args[1:]:
            if isinstance(arg, StringExecutor):
                argval = arg._str_value
                # GH vyper#3488
                if argval == "return_pc":
                    continue
                # calling convention wants to push the return pc since evm
                # has no subroutines, we are using python function call
                # machinery so we don't need to worry about that.
                if argval.startswith("_sym_"):
                    continue

            runtime_args.append(arg.analyze())

        self.args = runtime_args

        return self

    @cached_property
    def is_return_stmt(self):
        # i.e. we are exiting a subroutine
        return self.label == "return_pc"

    @cached_property
    def _argnames(self):
        if self.is_return_stmt:
            return ()
        return self.compile_ctx.labels[self.label].analyzed_param_names

    @cached_property
    def _type(self):
        if self.is_return_stmt:
            return None
        return self.compile_ctx.labels[self.label]._type

    @cached_property
    def _sig(self):
        # optimization assumption: they all need to be ints
        return tuple(int for _ in self._argnames)

    def _compile(self, *args):
        label = self.label

        if self.is_return_stmt:
            assert len(self.args) == 0
            self.builder.append("return")
            return

        argnames = self._argnames
        assert len(argnames) == len(self.args)

        args_str = ", ".join(["CTX"] + argnames)
        return f"{label}({args_str})"


@executor
class ExitTo(Goto):
    # exit_to and goto have pretty much the same semantics as far as we
    # are concerned here.
    _name = "exit_to"


@executor
class Label(IRExecutor):
    _name = "label"

    @cached_property
    def analyzed_param_names(self):
        _, var_list, _ = self.args
        return [x.out_name for x in var_list.args if x.varname != "return_pc"]

    def analyze(self):
        name, var_list, body = self.args

        self.labelname = name._str_value

        self.compile_ctx.add_label(self.labelname, self)

        with self.compile_ctx.allocate_local_frame():
            params = [param._str_value for param in var_list.args]
            with self.compile_ctx.variables(params):
                var_list = var_list.analyze()
                body = body.analyze()

        self.args = name, var_list, body

        self._type = body._type

        return self

    def compile(self, **kwargs):
        pass

    def compile_func(self):
        _, _, body = self.args
        params_str = ", ".join(["CTX"] + self.analyzed_param_names)
        with self.builder.block(f"def {self.labelname}({params_str})"):
            self.builder.append("VM = CTX.computation")
            body.compile()


@executor
class UniqueSymbol(IRExecutor):
    _name = "unique_symbol"

    def analyze(self):
        # we don't really need to do this analysis since vyper should
        # have done it already, but doesn't hurt to be a little paranoid
        symbol = self.args[0]._str_value
        self.compile_ctx.add_unique_symbol(symbol)
        return self

    def compile(self, **kwargs):
        pass


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

        self._type = body._type

        return self

    def compile(self, out=None, out_typ=None):
        variable, val, body = self.args
        # optimization assumption: most variables that
        # will be hotspots need to be ints.
        val.compile(out=variable.out_name, out_typ=int)
        return body.compile(out=out, out_typ=out_typ)


@executor
class Set(IRExecutor):
    _name = "set"

    def compile(self, **kwargs):
        variable, val = self.args
        val.compile(out=variable.out_name, out_typ=int)


def executor_from_ir(ir_node, vyper_compiler_data) -> Any:
    ret = _executor_from_ir(ir_node, CompileContext(vyper_compiler_data))

    ret = ret.analyze()
    ret.compile_main()
    return ret


def _executor_from_ir(ir_node, compile_ctx) -> Any:
    instr = ir_node.value
    if isinstance(instr, int):
        return IntExecutor(compile_ctx, instr)

    args = [_executor_from_ir(arg, compile_ctx) for arg in ir_node.args]

    if instr in _executors:
        return _executors[instr](ir_node, compile_ctx, *args)

    if (mnemonic := instr.upper()) in OPCODES:
        opcode_info = OpcodeInfo.from_mnemonic(mnemonic)
        return OpcodeIRExecutor(instr, opcode_info, ir_node, compile_ctx, *args)

    assert len(ir_node.args) == 0, ir_node
    assert isinstance(ir_node.value, str)
    return StringExecutor(compile_ctx, ir_node.value)

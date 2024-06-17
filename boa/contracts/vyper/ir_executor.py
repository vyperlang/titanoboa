import contextlib
import inspect
import textwrap
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import PurePath
from typing import Any, Optional

import vyper.ir.optimizer
from eth.exceptions import Halt
from eth.exceptions import Revert as VMRevert
from eth.exceptions import WriteProtection
from eth_hash.auto import keccak
from vyper.ast.nodes import VyperNode
from vyper.codegen.ir_node import IRnode
from vyper.compiler.phases import CompilerData
from vyper.evm.opcodes import OPCODES
from vyper.ir.compile_ir import getpos
from vyper.utils import unsigned_to_signed

from boa.util.lrudict import lrudict
from boa.vm.fast_mem import FastMem
from boa.vm.utils import ceil32, to_bytes, to_int

_keccak_cache = lrudict(256)


# note: This is used in the generated code for `Sha3_64` below.
def keccak256(x):
    return _keccak_cache.setdefault_lambda(x, keccak)


def _mkalphanum(string):
    # map a string to only-alphanumeric chars
    return "".join([c if c.isalnum() else "_" for c in string])


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
    var_id: int = -1

    def __post_init__(self):
        # use a global bc the generated functions need to be unique
        global _global_id
        self.uuid = str(_global_id)
        _global_id += 1

    @property
    def local_vars(self):
        return self.frames[-1].slots

    def freshvar(self, name=""):
        self.var_id += 1
        return f"var_{name}_{self.var_id}"

    @cached_property
    def contract_name(self):
        return _mkalphanum(PurePath(self.vyper_compiler_data.contract_path).name)

    def translate_label(self, label):
        return _mkalphanum(f"{self.contract_name}_{self.uuid}_{label}")

    def add_unique_symbol(self, symbol):
        if symbol in self.unique_symbols:  # pragma: no cover
            raise ValueError(
                "duplicated symbol {symbol}, this is likely a bug in vyper!"
            )
        self.unique_symbols.add(symbol)

    def add_label(self, labelname, executor):
        if labelname in self.labels:  # pragma: no cover
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
    _is_static = True  # can be used from a STATICCALL context

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

    # compile an IR "expr". called for its side effects on builder
    def compile(self, out=None, out_typ=None):
        # do a bit of metaprogramming to infer how to compile the args
        if hasattr(self, "_argnames"):
            argnames = self._argnames
        else:
            argnames = inspect.getargs(self._compile.__code__).args
            assert argnames[0] == "self"
            argnames = argnames[1:]

        argnames = [self.compile_ctx.freshvar(x) for x in argnames]

        self._compile_args(argnames)

        if hasattr(self, "_name"):
            self.builder.append(f"# {self.name}")

        if not self._is_static:
            _ = WriteProtection  # make flake8 happy
            self.builder.extend(
                """
            if VM.msg.is_static:
                raise WriteProtection(
                    "Cannot modify state while inside of a STATICCALL context"
                )
            """
            )

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

    def _compile(self, context):  # pragma: no cover
        raise RuntimeError("must be overridden in subclass!")

    def compile_main(self, contract_name=""):
        self.builder.extend("import vyper.utils\nimport _operator")

        main_name = self.compile_ctx.translate_label("main")
        with self.builder.block(f"def {main_name}(CTX)"):
            self.builder.append("VM = CTX.computation")
            self.compile()

        for func in self.compile_ctx.labels.values():
            self.builder.extend("\n\n")
            func.compile_func()

        py_file = f"{contract_name}{self.compile_ctx.uuid}.py"

        # uncomment for debugging the python code:
        # with open(py_file, "w") as f:
        #    print(self.builder.get_output(), file=f)

        py_bytecode = compile(self.builder.get_output(), py_file, "exec")
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
        assert -(2**255) <= self._int_value < 2**256
        self._int_value = _wrap256(self._int_value)  # wrap, could be negative
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
    _type: type = StackItem  # type: ignore

    def __init__(self, name: str, opcode_info: OpcodeInfo, *args):
        self.opcode_info = opcode_info

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


def wrap256_str(x_str):
    return f"(({x_str}) % 2**256)"


def _as_signed(x):
    return unsigned_to_signed(x, 256, strict=True)


# XXX: some of these do not need to be wrapped
class UnsignedBinopExecutor(IRExecutor):
    __slots__ = ("_name", "_op")
    _sig = int, int
    _type: type = int

    @cached_property
    def funcname(self):
        return self._op.__module__ + "." + self._op.__name__

    def _compile(self, x, y):
        return wrap256_str(f"{self.funcname}({x}, {y})")


class SignedBinopExecutor(UnsignedBinopExecutor):
    def _compile(self, x, y):
        return wrap256_str(f"{self.funcname}(_as_signed({x}), _as_signed({y}))")


# for binops, just use routines from vyper optimizer
for opname, (op, _, unsigned) in vyper.ir.optimizer.arith.items():
    base = UnsignedBinopExecutor if unsigned else SignedBinopExecutor
    nickname = opname.capitalize()
    _executors[opname] = type(nickname, (base,), {"_op": op, "_name": opname})


# shift instructions have opposite operand order from operator.*shift functions.
@executor
class Shr(IRExecutor):
    _name = "shr"
    _sig = (int, int)
    _type: type = int

    def _compile(self, bits, val):
        return f"{val} >> {bits}"


@executor
class Sar(IRExecutor):
    _name = "sar"
    _sig = (int, int)
    _type: type = int

    def _compile(self, bits, val):
        # wrap256 to get back into unsigned land
        return wrap256_str(f"_as_signed({val}) >> {bits}")


@executor
class Shl(IRExecutor):
    _name = "shl"
    _sig = (int, int)
    _type: type = int

    def _compile(self, bits, val):
        return wrap256_str(f"{val} << {bits}")


@executor
class Select(IRExecutor):
    _name = "select"
    _sig = (int, StackItem, StackItem)

    @cached_property
    def _type(self):
        _, x, y = self.args
        if x._type == y._type:
            return x._type
        return StackItem

    def _compile(self, test, x, y):
        return f"{x} if {test} else {y}"


_NULL_BYTE = repr(b"\x00")


@executor
class Caller(IRExecutor):
    _name = "caller"
    _sig = ()
    _type: type = bytes

    def _compile(self):
        return "VM.msg.sender"


@executor
class CalldataSize(IRExecutor):
    _name = "calldatasize"
    _sig = ()
    _type: type = int

    def _compile(self):
        return "len(VM.msg.data)"


@executor
class CallValue(IRExecutor):
    _name = "callvalue"
    _sig = ()
    _type: type = int

    def _compile(self):
        return "VM.msg.value"


@executor
class CalldataLoad(IRExecutor):
    _name = "calldataload"
    _sig = (int,)
    _type: type = bytes

    def _compile(self, ptr):
        self.builder.extend(
            f"""
            val = bytes(VM.msg.data[{ptr} : {ptr} + 32])
            """
        )
        return f"val.ljust(32, {_NULL_BYTE})"


@executor
class CalldataCopy(IRExecutor):
    _name = "calldatacopy"
    _sig = (int, int, int)

    def _compile(self, dst, src, size):
        self.builder.extend(
            f"""
            val = bytes(VM.msg.data[{src} : {src} + {size}])
            val = val.ljust({size}, {_NULL_BYTE})

            VM._memory.extend({dst}, {size})
            VM.memory_write({dst}, {size}, val)
            """
        )


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
    def immutables_size(self):
        compiler_data = self.compile_ctx.vyper_compiler_data
        return compiler_data.global_ctx.immutable_section_bytes


@executor
class DLoad(_CodeLoader):
    _name = "dload"
    _sig = (int,)
    _type: type = bytes

    def _compile(self, ptr):
        assert self.immutables_size > 0
        self.builder.extend(
            f"""
        code_start_position = {ptr} - {self.immutables_size} + len(VM.code)

        with VM.code.seek(code_start_position):
            ret = VM.code.read(32)
        """
        )
        return f"ret.ljust(32, {_NULL_BYTE})"


@executor
class DLoadBytes(_CodeLoader):
    _name = "dloadbytes"
    _sig = (int, int, int)

    def _compile(self, dst, src, size):
        assert self.immutables_size > 0

        # adapted from py-evm codecopy, but without gas metering, then
        # mess with the start position
        self.builder.extend(
            f"""
        code_start_position = {src} - {self.immutables_size} + len(VM.code)
        VM._memory.extend({dst}, {size})

        with VM.code.seek(code_start_position):
            code_bytes = VM.code.read({size})

        padded_code_bytes = code_bytes.ljust({size}, {_NULL_BYTE})

        VM.memory_write({dst}, {size}, padded_code_bytes)
        """
        )


@executor
class SLoad(IRExecutor):
    _name = "sload"
    _sig = (int,)
    _type = int

    def _compile(self, slot):
        return f"""VM.state.get_storage(address=VM.msg.storage_address, slot={slot})"""


@executor
class SStore(IRExecutor):
    _name = "sstore"
    _is_static = False
    _sig = (int, int)
    _type = int

    def _compile(self, slot, value):
        self.builder.extend(
            f"""
            VM.env._trace_sstore(VM.msg.storage_address, {slot})
            VM.state.set_storage(address=VM.msg.storage_address, slot={slot}, value={value})
            """
        )


@executor
class Sha3_64(IRExecutor):
    _name = "sha3_64"
    _sig = (bytes, bytes)

    # we need to trace for downstream to reverse engineer mappings
    def _compile(self, arg1, arg2):
        self.builder.extend(
            f"""
        preimage = {arg1}.rjust(32, {_NULL_BYTE}) + {arg2}.rjust(32, {_NULL_BYTE})
        image = keccak256(preimage)
        VM.env._trace_sha3_preimage(preimage, image)
        """
        )
        return "image"


@executor
class Sha3_32(IRExecutor):
    _name = "sha3_32"
    _sig = (bytes,)

    def _compile(self, arg):
        self.builder.extend(
            f"""
        preimage = {arg}.rjust(32, {_NULL_BYTE})
        """
        )
        return "keccak256(preimage)"


class _LogN(IRExecutor):
    @cached_property
    def _argnames(self):
        return ("ofst", "size") + tuple(f"log_arg{i}" for i in range(self.N))

    @cached_property
    def _sig(self):
        return (int, int) + tuple(int for _ in range(self.N))

    def _compile(self, ofst, size, *topics):
        # write out tuple strings correctly, always need trailing comma
        topics = [f"{topic}," for topic in topics]
        self.builder.extend(
            f"""
            VM._memory.extend({ofst}, {size})
            log_data = VM.memory_read_bytes({ofst}, {size})
            VM.add_log_entry(
                account=VM.msg.storage_address,
                topics=({" ".join(topics)}),
                data=log_data,
            )
            """
        )


# generate log0..log4
for i in (0, 1, 2, 3, 4):
    opname = f"log{i}"
    _executors[opname] = type(opname.capitalize(), (_LogN,), {"N": i, "_name": opname})


@executor
class Ceil32(IRExecutor):
    _name = "ceil32"
    _sig = (int,)
    _type: type = int

    def _compile(self, x):
        _ = ceil32  # typing hint
        return f"ceil32({x})"


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
        if len(self.args) == 0:
            self.builder.append("pass")
            return
        for i, arg in enumerate(self.args):
            if i + 1 < len(self.args):
                # don't accidentally assign
                arg.compile(out=None)
            else:
                return arg.compile(out=out, out_typ=out_typ)
        else:  # pragma: no cover
            raise RuntimeError("loop should have broken")


@executor
class Repeat(IRExecutor):
    _name = "repeat"

    def compile(self, out=None, out_typ=None):
        i_var, start, rounds, rounds_bound, body = self.args

        startname = self.compile_ctx.freshvar("start")
        roundsname = self.compile_ctx.freshvar("rounds")
        start.compile(startname, out_typ=int)
        rounds.compile(roundsname, out_typ=int)

        end = f"{startname} + {roundsname}"

        self.builder.append(f"assert {roundsname} <= {rounds_bound}")
        with self.builder.block(f"for {i_var.out_name} in range({startname}, {end})"):
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

        testname = self.compile_ctx.freshvar("test")
        test.compile(testname, out_typ=int)

        with self.builder.block(f"if bool({testname})"):
            body.compile(out, out_typ)

        if orelse:
            with self.builder.block("else"):
                orelse.compile(out, out_typ)


@executor
class Assert(IRExecutor):
    _name = "assert"
    _sig = (int,)

    def _compile(self, test):
        _ = VMRevert  # make flake8 happy
        self.builder.extend(
            f"""
        if not bool({test}):
            VM.vyper_source_pos = {repr(_get_ir_pos(self.ir_node))}
            VM.vyper_error_msg = {repr(self.ir_node.error_msg)}
            raise VMRevert("")  # venom assert
        """
        )


@executor
class _IRRevert(IRExecutor):
    _name = "revert"
    _sig = (int, int)

    def _compile(self, ptr, size):
        self.builder.extend(
            f"""
            VM.output = VM.memory_read_bytes({ptr}, {size})
            VM.vyper_source_pos = {repr(_get_ir_pos(self.ir_node))}
            VM.vyper_error_msg = {repr(self.ir_node.error_msg)}
            raise VMRevert(VM.output)  # venom revert
        """
        )


@executor
class Return(IRExecutor):
    _name = "return"
    _sig = (int, int)

    def _compile(self, ptr, size):
        _ = Halt  # make flake8 happy
        self.builder.extend(
            f"""
            VM.output = VM.memory_read_bytes({ptr}, {size})
            raise Halt("")  # return
        """
        )


@executor
class Stop(IRExecutor):
    _name = "stop"
    _sig = ()

    def _compile(self):
        self.builder.extend(
            """
            raise Halt("")  # return
            """
        )


@executor
class VarList(IRExecutor):
    _name = "var_list"


@executor
class Goto(IRExecutor):
    _name = "goto"

    is_return_stmt = False

    def analyze(self):
        self.label = self.compile_ctx.translate_label(self.args[0]._str_value)

        # just get the parameters, leaving the label in self.args
        # messes with downstream machinery which tries to analyze the label.
        runtime_args = []
        for arg in self.args[1:]:
            if isinstance(arg, Symbol):
                # we don't need to push the return pc on the way in.
                continue

            runtime_args.append(arg.analyze())

        self.args = runtime_args

        return self

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
        argnames = self._argnames
        assert len(argnames) == len(self.args)

        args_str = ", ".join(["CTX"] + list(args))
        return f"{self.label}({args_str})"


@executor
class ExitTo(Goto):
    # exit_to is similar but it is known to end execution of this subroutine
    _name = "exit_to"

    def analyze(self):
        # small helper function
        def _is_return_pc(arg):
            return isinstance(arg, StringExecutor) and arg._str_value == "return_pc"

        if _is_return_pc(self.args[0]):
            assert len(self.args) == 1
            self.is_return_stmt = True

        # strip out return_pc args, we don't need actually need to
        # generate any code for it
        self.args = [arg for arg in self.args if not _is_return_pc(arg)]

        if len(self.args) == 0:
            # it's not really a goto, it's a return statement
            # skip super.analyze() as it will choke on no args
            assert self.is_return_stmt
            return self

        return super().analyze()

    def _compile(self, *args):
        if self.is_return_stmt:
            # straight return
            # skip super._compile() as it will choke on no args
            assert len(self.args) == 0
            self.builder.append("return")
            return

        # execute the subroutine and then return
        # (probably not necessary to return the result but may as well)
        subroutine_call = super()._compile(*args)
        return f"return {subroutine_call}"


@executor
class CleanupRepeat(IRExecutor):
    # a no-op from our perspective
    _name = "cleanup_repeat"
    _sig = ()
    _argnames = ()

    def _compile(self):
        self.builder.append("pass")


@executor
class Break(IRExecutor):
    _name = "break"
    _sig = ()
    _argnames = ()

    def _compile(self):
        self.builder.append("break")


@executor
class Continue(IRExecutor):
    _name = "continue"
    _sig = ()
    _argnames = ()

    def _compile(self):
        self.builder.append("continue")


@executor
class Label(IRExecutor):
    _name = "label"

    @cached_property
    def analyzed_param_names(self):
        _, var_list, _ = self.args
        return [x.out_name for x in var_list.args if x.varname != "return_pc"]

    def analyze(self):
        name, var_list, body = self.args

        # use translate_label to ensure no collisions across compilations
        name._str_value = self.compile_ctx.translate_label(name._str_value)

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
class Symbol(IRExecutor):
    # in IR, a "symbol" is a label which needs to be pushed to the
    # stack for the calling convention.
    _name = "symbol"


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


def _ensure_ast_source(
    ir_node: IRnode, ast_source: VyperNode = None, error_msg: str = None
):
    if ir_node.ast_source is None:
        ir_node.ast_source = ast_source
    if ir_node.error_msg is None:
        ir_node.error_msg = error_msg
    for arg in ir_node.args:
        _ensure_ast_source(arg, ir_node.ast_source, ir_node.error_msg)


def executor_from_ir(ir_node, vyper_compiler_data) -> Any:
    _ensure_ast_source(ir_node)
    ctx = CompileContext(vyper_compiler_data)
    ret = _executor_from_ir(ir_node, ctx)

    ret = ret.analyze()

    # TODO: rename this, this is "something.vy", but we maybe want
    # "something.py <compiled from .vy>"
    ret.compile_main(ctx.contract_name)
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


def _get_ir_pos(ir_node):
    if ir_node.ast_source is None:
        return None
    return getpos(ir_node.ast_source)

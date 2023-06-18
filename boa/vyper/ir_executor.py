import contextlib
import re
from dataclasses import dataclass, field
from functools import cached_property
from typing import Any, Optional

import vyper.ir.optimizer
from eth.exceptions import Revert
from eth.vm.memory import Memory
from vyper.evm.opcodes import OPCODES
from vyper.utils import unsigned_to_signed


def debug(*args, **kwargs):
    print(*args, **kwargs)


def ceil32(x):
    return (x + 31) & ~31


@dataclass
class OpcodeInfo:
    # model of an opcode from vyper.evm.opcodes
    opcode: int  # opcode number ex. 0x01 for ADD
    consumes: int  # number of stack items this consumes
    produces: int  # number of stack items this produces, must be 0 or 1
    _gas_estimate: int  # in vyper.evm.opcodes but not useful

    def __post_init__(self):
        assert self.produces in (0, 1)

    @classmethod
    def from_opcode_info(cls, opcode_info):
        # info from vyper.evm.opcodes
        opcode, consumes, produces, gas_estimate = opcode_info
        return cls(opcode, consumes, produces, gas_estimate)


@dataclass(slots=True)
class EvalContext:
    ir_executor: "IRBaseExecutor"
    computation: Any  # ComputationAPI
    call_frames: list[list[Any]] = field(default_factory=list)

    def __post_init__(self):
        self.computation._memory = FastMem()

    def run(self):
        try:
            self._allocate_local_frame([], self.ir_executor._max_var_height)
            self.ir_executor.eval(self)
            return self.computation
        finally:
            # clear all state
            self.call_frames = []

    @property
    def local_vars(self):
        return self.call_frames[-1]

    def _allocate_local_frame(self, arglist, max_var_height):
        # pre-allocate variable slots so we don't waste time with append/pop.

        required_dummies = max_var_height + 1 - len(arglist)

        frame_vars = list(arglist)

        # a sentinel which will cause an exception if somebody tries to use it by accident
        dummy = "uh oh!"
        frame_vars.extend([dummy] * required_dummies)

        self.call_frames.append(frame_vars)

    @contextlib.contextmanager
    def allocate_local_frame(self, arglist, max_var_height):
        self._allocate_local_frame(arglist, max_var_height)
        yield
        self.call_frames.pop()

    def goto(self, compile_ctx, label, arglist):
        # special case to handle how vyper returns from subroutines
        if label == "returnpc":
            return

        compile_ctx.labels[label].execute_subroutine(self, *arglist)


@dataclass
class FrameInfo:
    current_slot: int = 0  # basically the de bruijn index
    slots: dict[str, int] = field(default_factory=lambda: {})

    # record the largest slot we see, so we know how many local vars to allocate
    max_slot: int = 0


@dataclass
class CompileContext:
    labels: dict[str, "IRBaseExecutor"]
    frames: list[FrameInfo] = field(default_factory=lambda: [FrameInfo()])

    @property
    def local_vars(self):
        return self.frames[-1].slots

    @contextlib.contextmanager
    def allocate_local_frame(self):
        frame = FrameInfo()
        self.frames.append(frame)
        yield frame
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
        frame.max_slot = max(frame.max_slot, frame.current_slot)

        yield

        for varname in vars_list:
            frame.current_slot -= 1
            if shadowed[varname] is None:
                del frame.slots[varname]
            else:
                frame.slots[varname] = shadowed[varname]


class IRBaseExecutor:
    __slots__ = ("args", "compile_ctx")

    def __init__(self, compile_ctx, *args):
        self.args = args
        self.compile_ctx = compile_ctx

    @cached_property
    def name(self):
        return self._name

    def __repr__(self):
        ret = self.name + "("

        def show(s):
            return hex(s) if isinstance(s, int) else repr(s)

        arg_reprs = [show(arg) for arg in self.args]
        arg_reprs = [x.replace("\n", "\n  ") for x in arg_reprs]
        ret += ",\n  ".join(arg_reprs)
        ret += ")"

        has_inner_newlines = any("\n" in t for t in arg_reprs)
        one_line_output = re.sub(r",\n *", ", ", ret).replace("\n", "")

        should_one_line = len(one_line_output) < 80 and not has_inner_newlines

        if should_one_line:
            return one_line_output
        else:
            return ret

    def eval(self, context):
        # debug("ENTER", self.name)
        args = self._eval_args(context)
        return self._impl(context, *args)

    def _eval_args(self, context):
        ret = [arg.eval(context) for arg in reversed(self.args)]
        ret.reverse()
        return ret

    def analyze(self):
        self.args = [arg.analyze() for arg in self.args]
        return self


@dataclass(slots=True)
class IntExecutor:
    _int_value: int

    def __repr__(self):
        return repr(self._int_value)

    def eval(self, context):
        return self._int_value

    def analyze(self):
        return self


@dataclass(slots=True)
class StringExecutor:
    _str_value: str
    compile_ctx: CompileContext

    def __repr__(self):
        return repr(self._str_value)

    def analyze(self):
        slot = self.compile_ctx.local_vars[self._str_value]
        return VariableExecutor(self._str_value, slot)


# an IR executor for evm opcodes which dispatches into py-evm
class OpcodeIRExecutor(IRBaseExecutor):
    def __init__(self, name, opcode_impl, opcode_info, *args):
        self.opcode_impl = opcode_impl  # py-evm OpcodeAPI
        self.opcode_info: OpcodeInfo = opcode_info  # info from vyper.evm.opcodes
        self._name = "__" + name + "__"  # to differentiate from implemented codes
        super().__init__(*args)

    @cached_property
    def produces(self):
        return self.opcode_info.produces

    def eval(self, context):
        # debug("ENTER", self.name)
        computation = context.computation
        for arg0 in reversed(self.args):
            arg = arg0.eval(context)
            if isinstance(arg, int):
                computation.stack_push_int(arg)
            elif isinstance(arg, bytes):
                computation.stack_push_bytes(arg)
            else:
                raise RuntimeError(f"Not a stack item. {type(arg)} {arg}")

        self.opcode_impl.__call__(computation)

        if self.produces:
            return computation.stack_pop1_any()


_executors = {}


# decorator to register an executor class in the _executors dict.
def executor(cls):
    _executors[cls._name] = cls
    return cls


StackItem = int | bytes


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


@dataclass(slots=True)
class VariableExecutor:
    varname: str
    var_slot: int

    def __repr__(self):
        return f"var({self.varname})"

    def eval(self, context):
        return context.local_vars[self.var_slot]


# most memory is aligned. treat it as list of ints, and provide mocking
# for instructions which access it in the slow way
class FastMem(Memory):
    __slots__ = ("mem_cache", "_bytes", "needs_writeback")

    def __init__(self):
        # XXX: check if this would be faster as dict?
        self.mem_cache = []  # cached words

        # words which are in the cache but have not been written
        # to the backing bytes
        self.needs_writeback = set()

        super().__init__()

    _DIRTY = object()

    def extend(self, start_position, size_bytes):
        # i.e. ceil32(len(self)) // 32
        new_size = (start_position + size_bytes + 31) // 32
        if (size_difference := new_size - len(self.mem_cache)) > 0:
            self.mem_cache.extend([self._DIRTY] * size_difference)
            super().extend(start_position, size_bytes)

    def read_word(self, start_position):
        if start_position % 32 == 0:
            if (ret := self.mem_cache[start_position // 32]) is not self._DIRTY:
                return ret

        ret = _to_int(self.read_bytes(start_position, 32))
        self.mem_cache[start_position // 32] = ret
        return ret

    def read_bytes(self, start_position, size):
        start = start_position // 32
        end = ceil32(start_position + size) // 32
        for ix in range(start, end):
            if ix in self.needs_writeback:
                super().write(ix * 32, 32, _to_bytes(self.mem_cache[ix]))
                self.needs_writeback.remove(ix)

        return super().read_bytes(start_position, size)

    def write_word(self, start_position, int_val):
        if start_position % 32 == 0:
            self.mem_cache[start_position // 32] = int_val

        self.needs_writeback.add(start_position // 32)

        # bypass cache dirtying
        # super().write(start_position, 32, _to_bytes(int_val))

    def write(self, start_position, size, value):
        start = start_position // 32
        end = (start_position + size + 31) // 32
        for i in range(start, end):
            self.mem_cache[i] = self._DIRTY
        super().write(start_position, size, value)


class IRExecutor(IRBaseExecutor):
    _sig = Optional[tuple]
    _max_var_height = None

    # a default eval implementation which is not super fast
    # but makes it convenient to implement executors.
    # for max perf, inline arg casting as in UnsignedBinopExecutor
    def eval(self, context):
        # debug("ENTER", self.name)
        args = self._eval_args(context)
        if self.sig_mapper:
            assert len(args) == len(self.sig_mapper)
            args = (mapper(arg) for (mapper, arg) in zip(self.sig_mapper, args))
        ret = self._impl(context, *args)
        # debug(f"({self.name} returning {ret})")
        return ret

    @cached_property
    def sig_mapper(self):
        return tuple(_to_int if typ is int else _to_bytes for typ in self._sig)


class UnsignedBinopExecutor(IRExecutor):
    __slots__ = ("_name", "_op")

    def eval(self, context):
        # debug("ENTER",self._name,self.args)
        x, y = self.args
        # note: eval in reverse order.
        y = _to_int(y.eval(context))
        x = _to_int(x.eval(context))
        return _wrap256(self._op(x, y))


class SignedBinopExecutor(UnsignedBinopExecutor):
    def eval(self, context):
        x, y = self.args
        # note: eval in reverse order.
        y = unsigned_to_signed(_to_int(y.eval(context), 256, strict=True))
        x = unsigned_to_signed(_to_int(x.eval(context), 256, strict=True))
        return _wrap256(self._op(x, y))


# for binops, just use routines from vyper optimizer
for opname, (op, _, unsigned) in vyper.ir.optimizer.arith.items():
    base = UnsignedBinopExecutor if unsigned else SignedBinopExecutor
    nickname = opname.capitalize()
    _executors[opname] = type(nickname, (base,), {"_op": op, "_name": opname})


@executor
class MLoad(IRExecutor):
    _name = "mload"

    def eval(self, context):
        # perf hotspot.
        ptr = _to_int(self.args[0].eval(context))
        context.computation._memory.extend(ptr, 32)
        # return context.computation._memory.read_bytes(ptr, 32)
        return context.computation._memory.read_word(ptr)


@executor
class MStore(IRExecutor):
    _name = "mstore"

    def eval(self, context):
        # perf hotspot.
        val = _to_int(self.args[1].eval(context))
        ptr = _to_int(self.args[0].eval(context))
        context.computation._memory.extend(ptr, 32)
        # context.computation._memory.write(ptr, 32, val)
        context.computation._memory.write_word(ptr, val)


@executor
class Ceil32(IRExecutor):
    _name = "ceil32"
    _sig = (int,)

    def _impl(self, context, x):
        return ceil32(x)


# @executor
class DLoad(IRExecutor):
    _name = "dload"
    _sig = (int,)

    def _impl(self, context, ptr):
        raise RuntimeError("unimplemented")


# @executor
class DLoadBytes(IRExecutor):
    _name = "dloadbytes"
    sig = (int, int, int)

    def _impl(self, context, dst, src, size):
        raise RuntimeError("unimplemented")


@executor
class Pass(IRExecutor):
    _name = "pass"

    def eval(self, context):
        pass


@executor
class Seq(IRExecutor):
    _name = "seq"

    def eval(self, context):
        lastval = None
        for arg in self.args:
            lastval = arg.eval(context)

        return lastval


@executor
class Repeat(IRExecutor):
    _name = "repeat"

    def eval(self, context):
        # debug("ENTER", self.name)
        i_var, start, rounds, rounds_bound, body = self.args

        start = start.eval(context)
        rounds = rounds.eval(context)
        assert rounds <= rounds_bound._int_value

        for i in range(start, start + rounds):
            context.local_vars[i_var.var_slot] = i
            body.eval(context)

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

    # override `eval()` so we can get the correct lazy behavior
    def eval(self, context):
        # debug("ENTER", self.name)
        try:
            test, body, orelse = self.args
        except ValueError:
            test, body = self.args
            orelse = None

        test = _to_int(test.eval(context))
        if bool(test):
            return body.eval(context)

        elif orelse is not None:
            return orelse.eval(context)

        return


@executor
class Assert(IRExecutor):
    _name = "assert"
    _sig = (int,)

    def _impl(self, context, test):
        if not bool(test):
            context.computation.output = b""
            raise Revert(b"")


@executor
class VarList(IRExecutor):
    _name = "var_list"


@executor
class Goto(IRExecutor):
    _name = "goto"

    @cached_property
    # figure out the label to jump to, works for both goto and exit_to
    # (why does vyper generate them differently? XXX fix in vyper)
    def label(self):
        ret = self.args[0]._str_value
        if ret.startswith("_sym_"):
            ret = ret[len("_sym_") :]
        return ret

    def analyze(self):
        for arg in self.args[1:]:
            arg = arg.analyze()
        return self

    def eval(self, context):
        # debug("ENTER", self.name)
        args = reversed([arg.eval(context) for arg in reversed(self.args[1:])])
        context.goto(self.compile_ctx, self.label, args)


@executor
class ExitTo(Goto):
    # exit_to and goto have pretty much the same semantics as far as we
    # are concerned here.
    _name = "exit_to"


@executor
class Label(IRExecutor):
    _name = "label"

    def __init__(self, compile_ctx, name, var_list, body):
        self.compile_ctx = compile_ctx
        self.var_list = var_list.args
        self.body = body
        self.labelname = name

        self.args = (name, var_list, body)

        compile_ctx.labels[name._str_value] = self

    def analyze(self):
        with self.compile_ctx.allocate_local_frame() as frame_info:
            var_list = [var._str_value for var in self.var_list]
            with self.compile_ctx.variables(var_list):
                self.body = self.body.analyze()

            # grab max slot after analysis
            self._max_var_height = frame_info.max_slot

        return self

    def eval(self, context):
        raise RuntimeError("labels should only be jumped into!")

    def execute_subroutine(self, context, *args):
        # assert len(args) == len(self.var_list), (list(args), self.var_list)
        with context.allocate_local_frame(args, self._max_var_height):
            self.body.eval(context)


@executor
class With(IRExecutor):
    _name = "with"

    # accessing local vars is a hotspot, so we translate varnames
    # to slots at compile time (something like de-bruijn index) to
    # save some dictionary accesses.
    def analyze(self):
        varname = self.args[0]._str_value
        val = self.args[1].analyze()  # analyze before shadowing

        with self.compile_ctx.variables([varname]):
            variable = self.args[0].analyze()
            body = self.args[2].analyze()

            self.args = (variable, val, body)

        return self

    def eval(self, context):
        variable, val, body = self.args

        val = val.eval(context)
        context.local_vars[variable.var_slot] = val
        ret = body.eval(context)

        return ret


def executor_from_ir(ir_node, opcode_impls: dict[int, Any]) -> Any:
    ret = _executor_from_ir(ir_node, opcode_impls, CompileContext({}))
    ret = ret.analyze()
    ret._max_var_height = ret.compile_ctx.frames[0].max_slot
    return ret


def _executor_from_ir(ir_node, opcode_impls, compile_ctx) -> Any:
    instr = ir_node.value
    if isinstance(instr, int):
        return IntExecutor(instr)

    args = [_executor_from_ir(arg, opcode_impls, compile_ctx) for arg in ir_node.args]

    if instr in _executors:
        return _executors[instr](compile_ctx, *args)

    if instr.upper() in OPCODES:
        opcode_info = OpcodeInfo.from_opcode_info(OPCODES[instr.upper()])
        opcode_impl = opcode_impls[opcode_info.opcode]
        return OpcodeIRExecutor(instr, opcode_impl, opcode_info, compile_ctx, *args)

    assert len(ir_node.args) == 0, ir_node
    assert isinstance(ir_node.value, str)
    return StringExecutor(instr, compile_ctx)

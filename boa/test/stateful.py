import boa
import sys
from collections import deque
from inspect import getmembers
from types import FunctionType
from typing import Any, Dict, Optional

from hypothesis import settings as hp_settings
from hypothesis import stateful as sf
from hypothesis.strategies import SearchStrategy

sf.__tracebackhide__ = True


class _BoaStateMachine:

    _failed = False

    def __init__(self) -> None:
        sf.RuleBasedStateMachine.__init__(self)

        self.snapshot_id = boa.env.vm.state.snapshot()

        if hasattr(self, "setup"):
            self.setup()  # type: ignore

    def execute_step(self, step):
        try:
            super().execute_step(step)
        except Exception:
            type(self)._failed = True
            raise

    def check_invariants(self, settings):
        try:
            super().check_invariants(settings)
        except Exception:
            type(self)._failed = True
            raise

    def teardown(self):
        pass
        #boa.env.vm.state.revert(self.snapshot_id)


def _member_filter(member: tuple) -> bool:
    attr, fn = member
    return (
        type(fn) is FunctionType
        and not hasattr(sf.RuleBasedStateMachine, attr)
        and not next((i for i in fn.__dict__.keys() if i.startswith("hypothesis_stateful")), False)
    )


def _attr_filter(attr: str, pattern: str) -> bool:
    return attr == pattern or attr.startswith(f"{pattern}_")


def _generate_state_machine(rules_object: type) -> type:

    bases = (_BoaStateMachine, rules_object, sf.RuleBasedStateMachine)
    machine = type("BoaStateMachine", bases, {})
    strategies: Dict = {k: v for k, v in getmembers(rules_object) if isinstance(v, SearchStrategy)}

    for attr, fn in filter(_member_filter, getmembers(machine)):
        varnames = [[i] for i in fn.__code__.co_varnames[1 : fn.__code__.co_argcount]]
        if fn.__defaults__:
            for i in range(-1, -1 - len(fn.__defaults__), -1):
                varnames[i].append(fn.__defaults__[i])

        if _attr_filter(attr, "initialize"):
            wrapped = sf.initialize(**{key[0]: strategies[key[-1]] for key in varnames})
            setattr(machine, attr, wrapped(fn))
        elif _attr_filter(attr, "invariant"):
            setattr(machine, attr, sf.invariant()(fn))
        elif _attr_filter(attr, "rule"):
            wrapped = sf.rule(**{key[0]: strategies[key[-1]] for key in varnames})
            setattr(machine, attr, wrapped(fn))

    return machine


def state_machine(
    rules_object: type, *args: Any, settings: Optional[dict] = None, **kwargs: Any
) -> None:

    machine = _generate_state_machine(rules_object)
    if hasattr(rules_object, "__init__"):
        # __init__ is treated as a class method
        rules_object.__init__(machine, *args, **kwargs)  # type: ignore

    try:
        sf.run_state_machine_as_test(
            machine, settings=hp_settings(**settings or {})
        )
        print("EXIT 2")
    finally:
        print("TEARDOWN")
        if hasattr(machine, "teardown_final"):
            # teardown_final is also a class method
            machine.teardown_final(machine)  # type: ignore

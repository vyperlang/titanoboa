from typing import Optional

from eth.abc import ComputationAPI

from boa import Env
from boa.environment import Address
from boa.util.exceptions import BoaError, strip_internal_frames


class _EvmContract:
    """
    Base class for the electrum virtual machine contracts:
    This includes ABI and Vyper contracts.
    """

    def __init__(
        self,
        env: Optional[Env] = None,
        filename: Optional[str] = None,
        address: Optional[Address] = None,
    ):
        self.env = env or Env.get_singleton()
        self._address = address  # this is overridden by subclasses
        self.filename = filename

    def stack_trace(self, computation: ComputationAPI):
        raise NotImplementedError

    def handle_error(self, computation):
        try:
            raise BoaError(self.stack_trace(computation))
        except BoaError as b:
            # modify the error so the traceback starts in userland.
            # inspired by answers in https://stackoverflow.com/q/1603940/
            raise strip_internal_frames(b) from None

    @property
    def address(self) -> Address:
        assert self._address is not None
        return self._address

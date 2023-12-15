import asyncio
import contextlib
import sys
from inspect import isawaitable, iscoroutinefunction
from typing import Any

import ipykernel.comm
import nest_asyncio
from eth_utils import to_checksum_address

from boa.integrations.jupyter.signer import _inject_javascript_triggers

ZMQ_POLLOUT = 2  # zmq.POLLOUT without zmq dependency

nest_asyncio.apply()


# adapted from:
# https://github.com/Kirill888/jupyter-ui-poll/blob/cb3fa2dbcb75/jupyter_ui_poll/_poll.py
class _UIComm(ipykernel.comm.Comm):
    # this entire class is cursed. do not touch!
    def __init__(self, *args, shell=None, loop=None, **kwargs):
        if loop is None:
            loop = asyncio.get_running_loop()
        self._loop = loop

        self._future = asyncio.futures.Future()

        if shell is None:
            shell = get_ipython()  # noqa: F821
        kernel = shell.kernel

        self._shell = shell
        self._kernel = kernel

        self._original_parent = (
            kernel._parent_ident,
            kernel.get_parent()  # ipykernel 6+
            if hasattr(kernel, "get_parent")
            else kernel._parent_header,  # ipykernel < 6
        )

        self._suspended_events: list[tuple[Any, Any, Any]] = []
        self._backup_execute_request = kernel.shell_handlers["execute_request"]

        if iscoroutinefunction(self._backup_execute_request):  # ipykernel 6+
            kernel.shell_handlers["execute_request"] = self._execute_request_async
        else:
            # ipykernel < 6
            kernel.shell_handlers["execute_request"] = self._execute_request

        shell.events.register("post_execute", self._post_execute_hook)

        super().__init__(*args, **kwargs)

    def _restore(self):
        if self._backup_execute_request is not None:
            self._kernel.shell_handlers[
                "execute_request"
            ] = self._backup_execute_request
            self._backup_execute_request = None

    def _reset_parent(self):
        self._kernel.set_parent(*self._original_parent)

    def _execute_request(self, stream, ident, parent):
        # store away execute request for later and reset io back to the original cell
        self._suspended_events.append((stream, ident, parent))
        self._reset_parent()

    async def _execute_request_async(self, stream, ident, parent):
        self._execute_request(stream, ident, parent)

    def _flush_stdio(self):
        sys.stdout.flush()
        sys.stderr.flush()

    async def _replay(self):
        k = self._kernel
        self._restore()

        shell_stream = getattr(k, "shell_stream", None)  # ipykernel 6 vs 5 differences

        for stream, ident, parent in self._suspended_events:
            k.set_parent(ident, parent)
            if k._aborting:
                k._send_abort_reply(stream, parent, ident)
            else:
                rr = k.execute_request(stream, ident, parent)
                if isawaitable(rr):
                    # note: cursed code. do not touch!
                    with self._preempt_current_task():
                        await rr

                # replicate shell_dispatch behaviour
                self._flush_stdio()

                if shell_stream is not None:  # 6+
                    k._publish_status("idle", "shell")
                    shell_stream.flush(ZMQ_POLLOUT)
                else:
                    k._publish_status("idle")

                await asyncio.sleep(0.001)

    async def do_one_iteration(self):
        try:
            rr = self._kernel.do_one_iteration()
            if isawaitable(rr):  # 6+
                await rr
        # except Exception:  # pylint: disable=broad-except
        #    # it's probably a bug in ipykernel,
        #    # .do_one_iteration() should not throw
        #    return
        finally:
            # reset stdio back to original cell
            self._flush_stdio()
            self._reset_parent()

    def _post_execute_hook(self, *args, **kwargs):
        self._shell.events.unregister("post_execute", self._post_execute_hook)
        self._restore()
        asyncio.ensure_future(self._replay(), loop=self._loop)

    async def _poll_async(self):
        while True:
            if self._future.done():
                return self._future.result()

            # give the buffers some time to flush.
            # but this is cursed! time.sleep does not work.
            await asyncio.sleep(0.001)

            await self.do_one_iteration()

    @staticmethod
    @contextlib.contextmanager
    def _preempt_current_task(loop=None):
        # use asyncio internals; suspend current task to avoid race conditions
        if loop is None:
            loop = asyncio.get_running_loop()
        try:
            # i.e., asyncio._leave_task(loop, tsk) with no checks
            tsk = asyncio.tasks._current_tasks.pop(loop, None)
            yield
        finally:
            # i.e., asyncio._enter_task(loop, tsk) with no checks
            if tsk is not None:
                asyncio.tasks._current_tasks[loop] = tsk
            else:
                asyncio.tasks._current_tasks.pop(loop, None)

    def poll(self):
        return self._loop.run_until_complete(self._poll_async())


# a test function
def foo():
    comm = _UIComm(target_name="test_comm")

    @comm.on_msg
    def _recv(msg):
        comm._future.set_result(msg)

    comm.send({"foo": "bar"})

    response = comm.poll()

    return response


class ColabSigner:
    def __init__(self, address=None):
        _inject_javascript_triggers()
        comm = _UIComm(target_name="get_signer")
        comm.on_msg(self._on_msg(comm))

        if address is not None:
            address = to_checksum_address(address)

        comm.send({"address": address})

        res = comm.poll()

        result_address = to_checksum_address(res["address"])

        if result_address != address and address is not None:
            raise ValueError(
                "signer returned by RPC is not what we wanted! "
                f"expected {address}, got {result_address}"
            )

        self.address = result_address

    @staticmethod
    # boilerplate
    def _on_msg(comm):
        def _recv(msg):
            try:
                res = msg["content"]["data"]
                if "success" not in res:
                    raise ValueError(res)
                comm._future.set_result(res["success"])
            except Exception as e:
                comm._future.set_exception(e)

        return _recv

    def send_transaction(self, tx_data):
        comm = _UIComm(target_name="send_transaction")

        comm.on_msg(self._on_msg(comm))

        comm.send({"transaction_data": tx_data, "account": self.address})

        response = comm.poll()

        # clean response
        def try_cast_int(s):
            # cast js bigint to string
            if isinstance(s, str) and s.isnumeric():
                return int(s)
            return s

        # TODO: use trim_dict util here
        response = {k: v for (k, v) in response.items() if bool(v)}

        # cast js bigint values
        response = {k: try_cast_int(v) for (k, v) in response.items()}

        return response

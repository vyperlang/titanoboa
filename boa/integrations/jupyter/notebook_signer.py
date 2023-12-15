"""
This module implements the NotebookSigner class, which is used to sign transactions in
Google Colab and Jupyter Notebook. For JupyterLab, see lab_signer.py.
"""
import asyncio
import contextlib
import sys
from inspect import isawaitable, iscoroutinefunction
from typing import Any

import ipykernel.comm
import nest_asyncio

from .utils import convert_frontend_dict, install_jupyter_javascript_triggers

ZMQ_POLLOUT = 2  # zmq.POLLOUT without zmq dependency


# adapted from:
# https://github.com/Kirill888/jupyter-ui-poll/blob/cb3fa2dbcb75/jupyter_ui_poll/_poll.py
class _UIComm(ipykernel.comm.Comm):
    # this entire class is cursed. do not touch!
    def __init__(self, *args, shell=None, loop=None, **kwargs):
        nest_asyncio.apply()
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

    @staticmethod
    def request(target_name, data=None):
        def _recv(msg):
            try:
                res = msg["content"]["data"]
                if "data" in res:
                    return comm._future.set_result(res["data"])
                raise Exception(res["error"])
            except Exception as e:
                comm._future.set_exception(e)

        comm = _UIComm(target_name=target_name)
        comm.on_msg(_recv)
        comm.send(data or {})
        return comm.poll()


class NotebookSigner:
    def __init__(self, address=None):
        install_jupyter_javascript_triggers()
        self.address = address

        if not address:
            self.address = _UIComm.request("loadSigner")

    def send_transaction(self, tx_data):
        response = _UIComm.request("signTransaction", tx_data)
        return convert_frontend_dict(response)

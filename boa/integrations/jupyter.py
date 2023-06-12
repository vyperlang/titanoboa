import asyncio
import contextlib
import sys
from inspect import isawaitable, iscoroutinefunction
from typing import Any

import ipykernel.comm
import IPython.display as frontend
import nest_asyncio
from eth_utils import to_checksum_address

ZMQ_POLLOUT = 2  # zmq.POLLOUT without zmq dependency

nest_asyncio.apply()

js = frontend.Javascript(
    """
require.config({
    paths: {
        //ethers: "https://cdnjs.cloudflare.com/ajax/libs/ethers/5.7.2/ethers.umd.min"
        ethers: "https://cdnjs.cloudflare.com/ajax/libs/ethers/6.4.2/ethers.umd.min"
    }
});

require(['ethers'], function(ethers) {
    // Initialize ethers
    let provider = new ethers.BrowserProvider(window.ethereum);

    // check that we have a signer for this account
    Jupyter.notebook.kernel.comm_manager.register_target('get_signer', function(c, msg) {
        // console.log("get_signer created", c)
        c.on_msg(function(msg) {
            // console.log("get_signer called", c)
            let account = msg.content.data.account
            provider.getSigner(account).then(signer => {
                // console.log("success", signer)
                c.send({"success": signer});
            }).catch(function(error) {
                console.error("got error, percolating up:", error);
                c.send({"error": error});
            });
        });
    });

    Jupyter.notebook.kernel.comm_manager.register_target("send_transaction", function(c, msg) {
        c.on_msg(function(msg) {
            let tx_data = msg.content.data.transaction_data;
            let account = msg.content.data.account
            provider.getSigner(account).then(signer => {
                signer.sendTransaction(tx_data).then(response => {
                    console.log(response);
                    c.send({"success": response});
                }).catch(function(error) {
                    console.error("got error, percolating up:", error);
                    c.send({"error": error});
                });
            }).catch(function(error) {
                console.error("got error, percolating up:", error);
                c.send({"error": error});
            });
        });
    });
});

Jupyter.notebook.kernel.comm_manager.register_target("test_comm", function(comm, msg) {
    console.log("ENTER", comm);
    /*comm.on_close(function(msg) {
        console.log("CLOSING", msg);
    });
    */

    comm.on_msg(function(msg) {
        console.log("ENTER 2", comm);
        console.log("ENTER 3", msg.content.data);
        setTimeout(() => {
            comm.send({"success": "hello", "echo": msg.content.data});
            comm.close();
            console.log(comm);
        }, 350);
    });
});
"""
)

frontend.display(js)


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


class BrowserSigner:
    def __init__(self, address=None):
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

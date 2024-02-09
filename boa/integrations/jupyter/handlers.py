"""
Handlers for the JupyterLab extension.
"""
import logging
from http import HTTPStatus
from multiprocessing.shared_memory import SharedMemory

from jupyter_server.base.handlers import APIHandler
from jupyter_server.serverapp import ServerApp
from jupyter_server.utils import url_path_join
from tornado.web import authenticated

from boa.integrations.jupyter.constants import NUL, PLUGIN_NAME, TOKEN_REGEX


class CallbackHandler(APIHandler):
    """
    Handler that receives a POST from jupyter.js when user interacts with their browser wallet.
    The token is used to identify the SharedMemory object to write the callback data to.
    Besides, the token needs to fulfill the expected regex that ensures it is a valid format.
    It expects the SharedMemory object has already been created via a BrowserSigner instance.
    """

    @authenticated  # ensure only authorized users can request the server
    def get(self, token: str):
        """Checks if a SharedMemory object with the given token exists."""
        try:
            memory = SharedMemory(token)
        except FileNotFoundError:
            self.set_status(HTTPStatus.NOT_FOUND)
            return self.finish({"error": f"Invalid token: {token}"})
        memory.close()
        self.set_status(HTTPStatus.NO_CONTENT)
        return self.finish()

    @authenticated  # ensure only authorized users can request the server
    def post(self, token: str):
        """Writes the request body to the SharedMemory object identified by the token."""
        body = self.request.body
        if not body:
            self.set_status(HTTPStatus.BAD_REQUEST)
            return self.finish({"error": "Request body is required"})

        try:
            memory = SharedMemory(token)
        except FileNotFoundError:
            self.set_status(HTTPStatus.NOT_FOUND)
            error = f"Invalid token: {token}"
            logging.warning(error)
            return self.finish({"error": error})

        try:
            memory.buf[: len(body) + 1] = body + NUL
        except ValueError:
            self.set_status(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            max_len = memory.size - len(NUL)
            error = (
                f"Request body has {len(body)} bytes, but only {max_len} are allowed"
            )
            return self.finish({"error": error})
        finally:
            memory.close()

        self.set_status(HTTPStatus.NO_CONTENT)
        return self.finish()


def setup_handlers(server_app: ServerApp) -> None:
    """
    Register the handlers in the Jupyter server.
    :param server_app: The Jupyter server application.
    """
    web_app = server_app.web_app
    base_url = url_path_join(web_app.settings["base_url"], PLUGIN_NAME)
    web_app.add_handlers(
        host_pattern=".*$",
        host_handlers=[(rf"{base_url}/callback/({TOKEN_REGEX})$", CallbackHandler)],
    )
    server_app.log.info(f"Handlers registered in {base_url}")

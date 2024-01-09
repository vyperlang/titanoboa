"""
Handlers for the JupyterLab extension.
"""
import logging
from http import HTTPStatus
from multiprocessing.shared_memory import SharedMemory

from jupyter_server.base.handlers import APIHandler
from jupyter_server.serverapp import ServerApp
from jupyter_server.utils import url_path_join
from tornado.web import Application, authenticated

from boa.integrations.jupyter.constants import PLUGIN_NAME, TOKEN_REGEX


class StatusHandler(APIHandler):
    def get(self):
        self.finish({"status": "ok"})


class CallbackHandler(APIHandler):
    """
    Handler that receives a POST from jupyter.js when user interacts with their browser wallet.
    The token is used to identify the SharedMemory object to write the callback data to.
    Besides, the token needs to fulfill the expected regex that ensures it is a valid format.
    It expects the SharedMemory object has already been created via a BrowserSigner instance.
    """

    @authenticated  # ensure only authorized user can request the Jupyter server
    def post(self, token: str):
        body = self.request.body
        if not body:
            self.set_status(HTTPStatus.BAD_REQUEST)
            return self.finish({"message": "Request body is required"})

        try:
            memory = SharedMemory(token)
        except FileNotFoundError:
            self.set_status(HTTPStatus.NOT_FOUND)
            return self.finish({"message": f"Invalid token: {token}"})

        try:
            body += b"\0"  # mark the end of the buffer
            memory.buf[: len(body)] = body
        except ValueError:
            self.set_status(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            message = f"Request body has {len(body)} bytes, but only {memory.size} are allowed"
            return self.finish({"message": message})
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
    web_app.add_handlers(host_pattern=".*$", host_handlers=create_handlers(base_url))
    server_app.log.info(f"Handlers registered in {base_url}")


def create_handlers(base_url="/") -> list[tuple[str, callable]]:
    """
    Create the handlers for the Jupyter server.
    :param base_url: The base URL for the handlers.
    :return: The list of handlers.
    """
    return [
        (rf"{base_url}$", StatusHandler),
        (rf"{base_url}/callback/({TOKEN_REGEX})$", CallbackHandler),
    ]


def start_server(port=8888) -> None:
    """
    Starts a separate tornado server with the handlers.
    This is used in Google Colab, where the server extension is not supported.
    """
    app = Application(create_handlers())
    try:
        app.listen(port)
        logging.info(f"JupyterLab boa server running on port {port}")
    except OSError as e:
        logging.warning(f"JupyterLab boa server could not listen port {port}: {e}")
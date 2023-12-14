from http import HTTPStatus
from multiprocessing.shared_memory import SharedMemory

import tornado
from jupyter_server.base.handlers import APIHandler
from jupyter_server.utils import url_path_join

BaseAPIHandler = APIHandler


class CallbackHandler(BaseAPIHandler):
    @tornado.web.authenticated  # ensure only authorized user can request the Jupyter server
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
            memory.buf[:len(body)] = body
        except ValueError:
            self.set_status(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            return self.finish({"message": f"Request body has {len(body)} bytes, but only {memory.size} are allowed"})
        finally:
            memory.close()

        self.set_status(HTTPStatus.NO_CONTENT)
        return self.finish()


def setup_handlers(server_app, name) -> None:
    """
    Register the handlers in the Jupyter server.
    :param server_app: The Jupyter server application.
    """
    web_app = server_app.web_app
    base_url = url_path_join(web_app.settings["base_url"], name)
    web_app.add_handlers(
        host_pattern=".*$",
        host_handlers=[(rf"{base_url}/callback/(\w+)", CallbackHandler)]
    )
    server_app.log.info(f"Handlers registered in {base_url}")

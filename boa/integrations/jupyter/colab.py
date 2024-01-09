import importlib.util
import logging
import re

from tornado.web import Application, RequestHandler

IN_GOOGLE_COLAB = importlib.util.find_spec("google.colab")


def start_server(port=8888) -> None:
    """
    Starts a separate tornado server with the handlers.
    This is used in Google Colab, where the server extension is not supported.
    """
    from boa.integrations.jupyter.handlers import (  # avoid circular import
        create_handlers,
    )

    app = Application(create_handlers())
    try:
        app.listen(port)
        logging.warning(f"JupyterLab boa server running on port {port}")
    except OSError as e:
        logging.warning(f"JupyterLab boa server could not listen port {port}: {e}")


class ColabHandler(RequestHandler):
    _ORIGIN = re.compile(r"https://.*\.googleusercontent\.com")

    def get_current_user(self):
        return True  # todo: check if user is authenticated

    def set_default_headers(self):
        if not self._ORIGIN.match(self.request.headers["Origin"]):
            self.set_status(403)
            return self.finish(
                {"message": f"Only requests from {self._ORIGIN.pattern} are allowed"}
            )

        self.set_header("Access-Control-Allow-Origin", self.request.headers["Origin"])

    def options(self, *args):
        self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.set_header("Access-Control-Request-Credentials", "true")
        self.set_header("Access-Control-Allow-Private-Network", "true")
        self.set_header("Access-Control-Allow-Headers", "*")
        self.set_status(204)  # No Content

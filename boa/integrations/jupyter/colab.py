import importlib.util
import logging
import re
from functools import cached_property
from http import HTTPStatus

from tornado.web import Application, RequestHandler

IN_GOOGLE_COLAB = importlib.util.find_spec("google.colab")


def start_server(port=8888) -> None:
    """
    Starts a separate tornado server with the handlers.
    This is used in Google Colab, where the server extension is not supported.
    """
    # import here to avoid circular import
    from boa.integrations.jupyter.handlers import create_handlers

    app = Application(create_handlers())
    try:
        app.listen(port)
        logging.warning(f"JupyterLab boa server running on port {port}")
    except OSError as e:
        logging.warning(f"JupyterLab boa server could not listen port {port}: {e}")


class ColabHandler(RequestHandler):
    _ORIGIN_PATTERN = re.compile(r"https://.*\.googleusercontent\.com")

    def get_current_user(self):
        return True  # todo: check if user is authenticated

    @cached_property
    def origin(self):
        return self.request.headers["Origin"] or self.request.host

    def set_default_headers(self):
        if not self._ORIGIN_PATTERN.match(self.origin):
            logging.warning(
                f"Only requests from {self._ORIGIN_PATTERN.pattern} are allowed, "
                f"not from {self.origin}"
            )
            return

        self.set_header("Access-Control-Allow-Origin", self.origin)

    def options(self, *args):
        if self._ORIGIN_PATTERN.match(self.origin):
            self.set_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.set_header("Access-Control-Request-Credentials", "true")
            self.set_header("Access-Control-Allow-Private-Network", "true")
            self.set_header("Access-Control-Allow-Headers", "*")
        self.set_status(HTTPStatus.NO_CONTENT)
        self.finish()

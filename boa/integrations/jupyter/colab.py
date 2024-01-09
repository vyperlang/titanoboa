import importlib.util
import logging

from tornado.web import Application

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

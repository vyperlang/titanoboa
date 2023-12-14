from boa.integrations.jupyter.handlers import setup_handlers
from boa.integrations.jupyter.signer import BrowserSigner


def load_jupyter_server_extension(server_app):
    server_app.log.warn("Loading titanoboa_jupyterlab extension via `load_jupyter_server_extension`.")
    __load_jupyter_server_extension(server_app)


def _load_jupyter_server_extension(server_app):
    server_app.log.warn("Loading titanoboa_jupyterlab extension via `__load_jupyter_server_extension`.")
    __load_jupyter_server_extension(server_app)


def __load_jupyter_server_extension(server_app):
    """Registers the API handler to receive HTTP requests from the frontend extension.

    Parameters
    ----------
    server_app: jupyterlab.labapp.LabApp
        JupyterLab application instance
    """
    name = "titanoboa_jupyterlab"
    setup_handlers(server_app, name)
    server_app.log.info(f"Registered {name} server extension")


__all__ = [
    BrowserSigner,
    _load_jupyter_server_extension,
    load_jupyter_server_extension,
]

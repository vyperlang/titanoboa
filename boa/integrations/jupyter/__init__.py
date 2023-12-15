from boa.integrations.jupyter.handlers import setup_handlers
from boa.integrations.jupyter.signer import BrowserSigner


def load_jupyter_server_extension(server_app):
    """Registers the API handler to receive HTTP requests from the frontend extension.

    Parameters
    ----------
    server_app: jupyterlab.labapp.LabApp
        JupyterLab application instance
    """
    name = "titanoboa_jupyterlab"
    setup_handlers(server_app, name)
    server_app.log.info(f"Registered {name} server extension")


# Reference the old function name with the new function name.
_load_jupyter_server_extension = load_jupyter_server_extension


__all__ = [BrowserSigner, load_jupyter_server_extension, _load_jupyter_server_extension]

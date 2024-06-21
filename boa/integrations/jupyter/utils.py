import json
import os
from os.path import dirname, join, realpath

from IPython.display import Javascript, display


def install_jupyter_javascript_triggers(debug_mode=False):
    """Run the ethers and titanoboa_jupyterlab Javascript snippets in the browser."""
    cur_dir = dirname(realpath(__file__))
    with open(join(cur_dir, "jupyter.js")) as f:
        js = f.read()

    prefix = os.getenv("JUPYTERHUB_SERVICE_PREFIX", "..")
    js = js.replace("$$JUPYTERHUB_SERVICE_PREFIX", prefix)
    js = js.replace("$$BOA_DEBUG_MODE", json.dumps(debug_mode))

    display(Javascript(js))


def convert_frontend_dict(data):
    """Convert the big integers and filter out empty values."""
    return {
        k: int(v) if isinstance(v, str) and v.isnumeric() else v
        for k, v in data.items()
        if v
    }

from os.path import dirname, join, realpath

import requests
from IPython.display import Javascript, display

from boa.integrations.jupyter.constants import ETHERS_JS_URL


def install_jupyter_javascript_triggers():
    """Run the ethers and titanoboa_jupyterlab Javascript snippets in the browser."""
    ethers_js = requests.get(ETHERS_JS_URL)

    cur_dir = dirname(realpath(__file__))
    with open(join(cur_dir, "jupyter.js")) as f:
        jupyter_js = f.read()

    display(Javascript(ethers_js.text + jupyter_js))


def convert_frontend_dict(data):
    """Convert the big integers and filter out empty values."""
    return {
        k: int(v) if isinstance(v, str) and v.isnumeric() else v
        for k, v in data.items()
        if v
    }

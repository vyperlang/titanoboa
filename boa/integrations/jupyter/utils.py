from os.path import dirname, join, realpath

import requests
from IPython.core.display import Javascript
from IPython.core.display_functions import display

from boa.integrations.jupyter.constants import ETHERS_JS_URL


def install_jupyter_javascript_triggers():
    """Run the ethers and titanoboa_jupyterlab Javascript snippets in the browser."""
    ethers_js = requests.get(ETHERS_JS_URL)
    display(Javascript(ethers_js.text))

    cur_dir = dirname(realpath(__file__))
    with open(join(cur_dir, "jupyter.js")) as f:
        display(Javascript(f.read()))


def convert_frontend_dict(sign_data):
    return {
        k: int(v) if isinstance(v, str) and v.isnumeric() else v
        for k, v in sign_data.items()
        if v
    }

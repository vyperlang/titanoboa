"""
Fake jupyter_server.utils module for testing without Jupyter server.
"""


def url_path_join(*args):
    return "/".join(args)

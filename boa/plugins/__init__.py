import importlib
import pkgutil


def LOAD_PLUGINS():
    for _, name, _ in pkgutil.iter_modules():
        if name.startswith("boa_"):
            importlib.import_module(name)

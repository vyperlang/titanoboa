# Simple context manager which functions like the `open()` builtin -
# if simply called, it never calls __exit__, but if used as a context manager,
# it calls __exit__ at scope exit
class Open:
    def __init__(self, get, set_, item):
        self.anchor = get()
        self._set = set_
        self._set(item)

    def __enter__(self):
        # dummy implementation, no-op
        pass

    def __exit__(self, *args):
        self._set(self.anchor)

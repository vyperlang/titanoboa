from contextlib import contextmanager


class JournalingDict(dict):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stack = []

    def enter_scope(self):
        self.stack.append([])

    def exit_scope(self):
        if not self.stack:
            raise IndexError("No scope to exit")

        changes = self.stack.pop()

        for key, old_value in reversed(changes):
            if old_value is None:
                super().__delitem__(key)
            else:
                super().__setitem__(key, old_value)

    def __setitem__(self, key, value):
        if self.stack:
            self.stack[-1].append((key, self.get(key, None)))
        super().__setitem__(key, value)

    def __delitem__(self, key):
        if self.stack:
            self.stack[-1].append((key, self.get(key, None)))
        super().__delitem__(key)

    @contextmanager
    def scoped(self):
        self.enter_scope()
        try:
            yield
        finally:
            self.exit_scope()

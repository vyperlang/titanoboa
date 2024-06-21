class lrudict(dict):
    def __init__(self, n, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.n = n

    def __getitem__(self, k):
        val = super().__getitem__(k)
        del self[k]  # move to the front of the queue
        super().__setitem__(k, val)
        return val

    def __setitem__(self, k, val):
        if len(self) == self.n and k not in self:
            del self[next(iter(self))]
        super().__setitem__(k, val)

    # set based on a lambda
    def setdefault_lambda(self, k, fn):
        try:
            return self[k]
        except KeyError:
            self[k] = (ret := fn(k))
            return ret

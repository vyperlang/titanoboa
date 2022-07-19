import IPython.core.magic as ipython

import boa

_ = None
_contracts = {}


@ipython.magics_class
class TitanoboaMagic(ipython.Magics):
    @ipython.cell_magic
    def vyper(self, line, cell):
        line = line or None
        c = boa.loads_partial(cell, name=line)
        if line:
            self.shell.user_ns[line] = c  # ret available in user ipython locals
            _contracts[line] = c  # ret available in boa.ipython._contracts
        _ = c  # ret available at `boa.ipython._`
        return c


def load_ipython_extension(ipy_module):
    ipy_module.register_magics(TitanoboaMagic)

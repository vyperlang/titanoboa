import IPython.core.magic as ipython

import boa


@ipython.magics_class
class TitanoboaMagic(ipython.Magics):
    @ipython.cell_magic
    def vyper(self, line, cell):
        line = line or None
        c = boa.loads_partial(cell, name=line)
        return c


def load_ipython_extension(ipy_module):
    ipy_module.register_magics(TitanoboaMagic())

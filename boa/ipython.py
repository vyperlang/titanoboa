import IPython.core.magic as ipython

import boa

_ = None
_contracts = {}


@ipython.magics_class
class TitanoboaMagic(ipython.Magics):
    @ipython.line_cell_magic
    def vyper(self, line, cell=None):
        if cell is None:
            return boa.eval(line)

        return self.contract(line, cell)

    # unsure about "vyper" vs "contract" cell magic; keep both until decided
    @ipython.cell_magic
    def contract(self, line, cell):
        line = line or None
        c = boa.loads_partial(cell, name=line)
        if line:
            self.shell.user_ns[line] = c  # ret available in user ipython locals
            _contracts[line] = c  # ret available in boa.ipython._contracts
        _ = c  # ret available at `boa.ipython._`
        return c

    # unsure about "vyper" vs "eval" line magic; keep both until decided
    @ipython.line_magic
    def eval(self, line):
        return boa.eval(line)


def load_ipython_extension(ipy_module):
    ipy_module.register_magics(TitanoboaMagic)

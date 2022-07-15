import IPython.core.magic as ipython
import shlex
import boa

# The class MUST call this class decorator at creation time
@ipython.magics_class
class TitanoboaMagic(ipython.Magics):

    @ipython.cell_magic
    def vyper(self, line, cell):
        # note use of eval here is ok since everything is being
        # eval'ed anyway.
        args = [eval(arg) for arg in shlex.split(line)]
        c = boa.loads(cell, *args)
        return c

def load_ipython_extension(ipy_module):
    ipy_module.register_magics(TitanoboaMagic())

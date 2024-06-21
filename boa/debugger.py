import pdb

from vyper.exceptions import VyperException


class BoaDebug(pdb.Pdb):
    prompt = "(boa-debug) "

    def __init__(self, computation, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.contract = computation.msg._contract
        self.contract._computation = computation

    @property
    def intro(self):
        computation = self.contract._computation
        ast_source = self.contract.find_source_of(computation)
        if ast_source is not None:
            return str(VyperException("breakpoint at:", ast_source))

    def start(self):
        self.set_trace()

    def do_show_contract(self, *args):
        print(self.contract, file=self.stdout)

    def do_show_frame(self, *args):
        print(self.contract.debug_frame(), file=self.stdout)

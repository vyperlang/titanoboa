import cmd

from vyper.exceptions import VyperException


class BoaDebug(cmd.Cmd):
    prompt = "(boa-debug) "

    def __init__(self, computation, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.contract = computation.msg._contract
        self.contract._computation = computation

        ast_source = self.contract.find_source_of(computation.code)
        if ast_source is not None:
            print(VyperException("breakpoint at:", ast_source), file=self.stdout)

    def do_show_contract(self, *args):
        print(self.contract, file=self.stdout)

    def do_show_frame(self, *args):
        print(self.contract.debug_frame(), file=self.stdout)

    def do_EOF(self, *args):
        return True

    def do_continue(self, *args):
        return True

# an Environment which interacts with a real (prod or test) chain


def _computation_from_trace(trace):
    computation = lambda: None

    # per debug_traceTransaction. this seems not right though
    computation.output = bytes.fromhex(trace["output"].strip("0x"))

    return computation


class Chain(Env):
    has_vm = False

    _supports_traces = None

    def __init__(self, web3):
        self.web3 = web3

    @property
    def vm(self):
        raise RuntimeError("VM is not available in prod")

    def get_balance(self, account):
        return self.web3.eth.get_balance(account)

    def execute_code(
        self,
        to_address,
        sender=None,
        gas=None,
        value=0,
        bytecode=b"",
        data=b"",
        start_pc=0,
        fake_codesize=None,
    ):
        # pseudo code
        tx_data = dict(sender=sender, gas=gas, value=value, data=data)

        if self.eoa not in self._accounts:
            raise ValueError(f"Account not available: {self.eoa}")

        signed = self._accounts[eoa].sign_transaction(tx_data)

        tx_hash = self.web3.send_raw_transaction(signed.rawTransaction)

        self.web3.wait_for_transaction_receipt(tx_hash)

        trace = self.web3.provider.make_request("debug_traceTransaction", tx_hash)

        computation = computation_from_trace(trace)

        return computation

    def deploy_code(
        self,
        deploy_to=ZERO_ADDRESS,
        sender=None,
        gas=None,
        value=0,
        bytecode=b"",
        data=b"",
        start_pc=0,
    ):
        # pseudo code
        pass

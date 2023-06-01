# an Environment which interacts with a real (prod or test) chain


def _computation_from_trace(trace):
    computation = lambda: None

    # per debug_traceTransaction. construct a fake computation.
    computation.output = bytes.fromhex(trace.get("output", "").strip("0x"))

    return computation


class Chain(Env):
    has_vm = False

    _supports_traces = None

    def __init__(self, rpc_url):
        self._rpc_url = rpc_url

    @cached_property
    def session(self):
        return requests.Session()

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
        _, trace = self._tx_helper(
            from_=sender, to=to_address, value=value, gas=gas, data=data
        )

    def deploy_code(self, sender=None, gas=None, value=0, bytecode=b"", data=b""):
        _, trace = self._tx_helper(
            from_=sender,
            to=to_checksum_address(ZERO_ADDRESS),
            value=value,
            gas=gas,
            data=bytecode,
        )
        return _computation_from_trace(trace)

    def _tx_helper(self, from_, to, gas=None, value=None, data=b""):
        # pseudo code
        tx_data = {"from": from_, "to": to, "gas": gas, "value": value, "data": data}
        sender = self.eoa if sender is None else sender

        if sender not in self._accounts:
            raise ValueError(f"Account not available: {self.eoa}")

        signed = self._accounts[eoa].sign_transaction(tx_data)

        tx_hash = self.web3.send_raw_transaction(signed.rawTransaction)

        self.web3.wait_for_transaction_receipt(tx_hash)

        # works with alchemy
        trace = self.web3.provider.make_request(
            "debug_traceTransaction",
            [tx_hash, {"tracer": "callTracer", "tracerConfig": {"onlyTopCall": True}}],
        )

        return tx_hash, trace

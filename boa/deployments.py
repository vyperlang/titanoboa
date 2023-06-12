

class DeploymentLogger:
    # pseudocode

    def __init__(self, deploy_id):
        self._deploy_id = deploy_id

    def init_deployment(self):
        self._acquire_lock()

    def finish_deployment(self):
        self.db["state"] = "done"

        self._write()

    def add_tx_hash(self, tx_hash):
        self.db["tx_hashes"].append(tx_hash)

        self._write()

    def add_receipt(self, tx_hash, receipt):
        self.db["receipts"][tx_hash] = receipt

        self._write(flush=False)

    @property
    def receipts(self):
        return self.db["receipts"]

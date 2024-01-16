from datetime import timedelta

CALLBACK_TOKEN_TIMEOUT = timedelta(minutes=3)
MEMORY_LENGTH = 50 * 1024  # Size of the shared memory object
CALLBACK_TOKEN_BYTES = 32
NUL = b"\0"
ETHERS_JS_URL = "https://cdnjs.cloudflare.com/ajax/libs/ethers/6.9.0/ethers.umd.min.js"
PLUGIN_NAME = "titanoboa_jupyterlab"
TOKEN_REGEX = rf"{PLUGIN_NAME}_[0-9a-fA-F]{{{CALLBACK_TOKEN_BYTES * 2}}}"
TRANSACTION_TIMEOUT_MESSAGE = (
    "Timeout waiting for user to confirm transaction in the browser wallet plug-in."
)
ADDRESS_TIMEOUT_MESSAGE = "Timeout loading browser browser wallet plug-in."

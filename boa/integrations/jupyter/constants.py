from datetime import timedelta

NUL = b"\0"
CALLBACK_TOKEN_TIMEOUT = timedelta(minutes=3)
SHARED_MEMORY_LENGTH = 100 * 1024 + len(NUL)  # Size of the shared memory object
CALLBACK_TOKEN_CHARS = 30  # OSx limits this to 31 characters
PLUGIN_NAME = "titanoboa_jupyterlab"
TOKEN_REGEX = rf"[0-9a-fA-F]{{{CALLBACK_TOKEN_CHARS}}}"
TRANSACTION_TIMEOUT_MESSAGE = (
    "Timeout waiting for user to confirm transaction in the browser wallet plug-in."
)
ADDRESS_TIMEOUT_MESSAGE = "Timeout loading browser browser wallet plug-in."
RPC_TIMEOUT_MESSAGE = "Timeout waiting for response from RPC."

from datetime import timedelta

CALLBACK_TOKEN_TIMEOUT = timedelta(minutes=3)
ADDRESS_LENGTH = 42
TRANSACTION_JSON_LENGTH = 2048  # max length of a transaction JSON
CALLBACK_TOKEN_BYTES = 32
NUL = b"\0"

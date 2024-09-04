import time


class Retry(ValueError):
    ...


def retry_fn(
    fn, exception=Retry, num_retries=10, backoff_ms=400, exponential_factor=1.1
):
    """
    Retry a function call (no arguments, use retry() decorator or lambda otherwise).
    It supports exponential backoff and a maximum number of retries.
    :param fn: The function to retry.
    :param exception: The exception to catch.
    :param num_retries: The number of times to retry.
    :param backoff_ms: The backoff time in milliseconds.
    :param exponential_factor: The exponential factor to use.
    :return: The result of the function call.
    """
    for i in range(num_retries):
        try:
            return fn()
        except exception as e:
            if i + 1 == num_retries:
                raise e
            time.sleep(backoff_ms * (exponential_factor**i))


def retry(*args, **kwargs):
    """
    A decorator for retrying a function call with support for arguments.
    :param args: The arguments to pass to retry.
    :param kwargs: The keyword arguments to pass to retry.
    :return: A decorator that retries the function call.
    """

    def decorator(fn):
        """:return: A new function that is decorated with retry."""

        def wrapper(*fn_args, **fn_kwargs):
            """:return: The result of retrying the function call."""

            def decorated():
                """:return: The result of the function call which may be retried."""
                return fn(*fn_args, **fn_kwargs)

            return retry_fn(decorated, *args, **kwargs)

        return wrapper

    return decorator

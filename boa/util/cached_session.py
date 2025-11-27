from typing import Optional
from requests import Response, Session


def get_session(callback: Optional[callable] = lambda _: True) -> Optional[Session]:
    """Returns a session for making HTTP requests.
    If the `requests_cache` library is available, it will return a `CachedSession`.
    Else it will return a regular `Session`.
    """
    SESSION = None

    try:
        from requests_cache import CachedSession

        def filter_fn(response: Response) -> bool:
            return response.ok and callback(response.json())

        SESSION = CachedSession(
            "~/.cache/titanoboa/explorer_cache",
            filter_fn=filter_fn,
            allowable_codes=[200],
            cache_control=True,
            expire_after=3600 * 6,
            stale_if_error=True,
            stale_while_revalidate=True,
        )
    except ImportError:
        from requests import Session

        SESSION = Session()

    return SESSION

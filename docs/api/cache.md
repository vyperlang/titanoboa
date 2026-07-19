# Cache

## `set_cache_dir`

!!! function "`boa.interpret.set_cache_dir(cache_dir='~/.cache/titanoboa')`"

    **Description**

    Set the disk-cache directory for Vyper compilation results. The default is
    `~/.cache/titanoboa`. Passing `None` disables compilation caching.

    These helpers are defined in `boa.interpret`; they are not exported as
    `boa.set_cache_dir` or `boa.disable_cache`.

    ---

    **Parameters**

    - `cache_dir`: The directory to store the cache files.

    ```python
    from pathlib import Path

    from boa.interpret import set_cache_dir

    set_cache_dir(Path.home() / ".cache" / "my-project" / "titanoboa")
    ```

## `disable_cache`

!!! function "`boa.interpret.disable_cache()`"

    **Description**

    Disable compilation caching. This is equivalent to
    `boa.interpret.set_cache_dir(None)`.

    ```python
    from boa.interpret import disable_cache

    disable_cache()
    ```

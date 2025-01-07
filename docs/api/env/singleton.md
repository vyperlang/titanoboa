# Pick your environment

This page documents the functions to set the singleton environment.
If you need help choosing an environment, see the [Titanoboa Environments](../../explain/singleton_env.md) page.

Note that all the `set_env` functions return an optional context manager.
See [context management](../../explain/singleton_env.md#automatic-context-management) section for more information.

<-- TODO: Document set_env APIs with !!!function -->

## `swap_env`
This is the same as `set_env`, but it **only** works in the context of a context manager.
Note the other set_env functions offer an optional usage of context manager, while `swap_env` requires it.

## `set_env`
## `fork`
<!-- TODO: this function is repeated in testing.md -->

## `set_browser_env`
## `set_network_env`
## `reset_env`

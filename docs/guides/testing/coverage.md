## Coverage

!!! warning
    Coverage is not yet supported when using [fast mode](../../api/env/env.md#enable_fast_mode).

Titanoboa offers coverage through the [coverage.py](https://coverage.readthedocs.io/) package.

To use, add the following to `.coveragerc`:

```
[run]
plugins = boa.coverage
```

(for more information see https://coverage.readthedocs.io/en/latest/config.html)

Then, run with `coverage run ...`

To run with pytest, we do the following:

```
pytest --cov= --cov-branch ...
```

Finally, `coverage.py` saves coverage data to a file named `.coverage` in the directory it is run in. To view the formatted coverage data, you typically want to use `coverage report` or `coverage html`. See more options at https://coverage.readthedocs.io/en/latest/cmd.html.

!!! note
    Coverage is experimental and there may be odd corner cases! If so, please report them on github or in the `#titanoboa-interpreter` channel of the [Vyper discord](https://discord.gg/6tw7PTM7C2).


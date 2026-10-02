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

To collect line and branch coverage with pytest:

```
pytest --cov=. --cov-branch ...
```

Finally, `coverage.py` saves coverage data to a file named `.coverage` in the directory it is run in. To view the formatted coverage data, you typically want to use `coverage report` or `coverage html`. See more options at https://coverage.readthedocs.io/en/latest/cmd.html.

## Branch coverage and optimization

When branch coverage is enabled and a contract does not explicitly select an optimization level, Titanoboa compiles it with Vyper's `OptimizationLevel.NONE`. This keeps conditional jumps aligned with source branches and emits a warning explaining the change. The effective optimization setting is included in the compilation-cache key, so coverage artifacts do not collide with normally optimized artifacts.

If code explicitly requests another optimization level, Titanoboa preserves that choice and warns that branch coverage may be inaccurate. Line hits are still recorded, but branch arcs for optimized contracts are skipped.

Start coverage before loading contracts whose branches you want to measure. Coverage state survives `boa.reset_env()`.

!!! note
    Coverage is experimental and there may be odd corner cases! If so, please report them on github or in the `#titanoboa-interpreter` channel of the [Vyper discord](https://discord.gg/6tw7PTM7C2).

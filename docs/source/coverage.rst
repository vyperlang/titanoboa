Using Coverage
==============

Titanoboa offers coverage through the `coverage.py <https://coverage.readthedocs.io/>`_ package.

To use, add the following to ``.coveragerc``:

.. code-block::

    [run]
    plugins = boa.coverage

(for more information see https://coverage.readthedocs.io/en/latest/config.html)

Then, run with ``coverage run ...``

To run with pytest, it can be invoked in either of two ways,

.. code-block::

    coverage run -m pytest ...

or,

.. code-block::

    pytest --cov= ...

`pytest-cov <https://pytest-cov.readthedocs.io/en/latest/readme.html#usage>`_ is a wrapper around ``coverage.py`` for using with pytest; using it is recommended because it smooths out some quirks of using ``coverage.py`` with pytest.

Finally, ``coverage.py`` saves coverage data to a file named ``.coverage`` in the directory it is run in. To view the formatted coverage data, you typically want to use ``coverage report`` or ``coverage html``. See more options at https://coverage.readthedocs.io/en/latest/cmd.html.

Coverage is experimental and there may be odd corner cases! If so, please report them on github or in the ``#titanoboa-interpreter`` channel of the `Vyper discord <https://discord.gg/6tw7PTM7C2>`_.

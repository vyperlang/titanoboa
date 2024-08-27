Testing with Titanoboa
======================

Titanoboa integrates natively with `pytest <https://docs.pytest.org/>`_ and `hypothesis <https://hypothesis.readthedocs.io/en/latest/quickstart.html>`_. Nothing special is needed to enable these, as the plugins for these packages will be loaded automatically. By default, isolation is enabled for tests - that is, any changes to the EVM state inside the test case will automatically be rolled back after the test case completes.

Since ``titanoboa`` is framework-agnostic any other testing framework should work as well.


Gas Profiling
-----------------------

Titanoboa has native gas profiling tools that store and generate statistics upon calling a contract. When enabled, gas costs are stored per call in global ``boa.env._cached_call_profiles`` and ``boa.env._cached_line_profiles`` dictionaries.
To enable gas profiling,

1. decorate tests with ``@pytest.mark.gas_profile``, or
2. run pytest with ``--gas-profile``, e.g. ``pytest tests/unitary --gas-profile``

If ``--gas-profile`` is selected, to ignore gas profiling for specific tests, decorate the test with ``@pytest.mark.ignore_gas_profiling``.

.. code-block:: python

    @pytest.mark.profile
    def test_profile():

        source_code = """
    @external
    @view
    def foo(a: uint256 = 0):
        x: uint256 = a
    """
        contract = boa.loads(source_code, name="FooContract")
        contract.foo()

.. code-block:: console

    ┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━┓
    ┃ Contract    ┃ Address                                    ┃ Computation ┃ Count ┃ Mean ┃ Median ┃ Stdev ┃ Min ┃ Max ┃
    ┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━┩
    │ FooContract │ 0x0000000000000000000000000000000000000066 │ foo         │ 1     │ 88   │ 88     │ 0     │ 88  │ 88  │
    └─────────────┴────────────────────────────────────────────┴─────────────┴───────┴──────┴────────┴───────┴─────┴─────┘


    ┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┓
    ┃ Contract                                             ┃ Computation                                                                ┃ Count ┃ Mean  ┃ Median ┃ Stdev ┃ Min   ┃ Max   ┃
    ┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━┩
    │ Path:                                                │                                                                            │       │       │        │       │       │       │
    │ Name: FooContract                                    │                                                                            │       │       │        │       │       │       │
    │ Address: 0x0000000000000000000000000000000000000066  │                                                                            │ Count │ Mean  │ Median │ Stdev │ Min   │ Max   │
    │ ---------------------------------------------------- │ -------------------------------------------------------------------------- │ ----- │ ----- │ -----  │ ----- │ ----- │ ----- │
    │ Function: foo                                        │   4: def foo(a: uint256 = 0):                                              │ 1     │ 73    │ 73     │ 0     │ 73    │ 73    │
    │                                                      │   5: x: uint256 = a                                                        │ 1     │ 15    │ 15     │ 0     │ 15    │ 15    │
    └──────────────────────────────────────────────────────┴────────────────────────────────────────────────────────────────────────────┴───────┴───────┴────────┴───────┴───────┴───────┘

.. note::
    Note that if a specific fixture is called in two separate tests, pytest will re-instantiate it. Meaning, if a Contract
    is deployed in a fixture, calling the fixture on tests in two separate files can lead to two deployments of that Contract,
    and hence two separate addresses in the profile table.

.. warning::
    Profiling does not work with pytest-xdist plugin at the moment.

Coverage
--------------

.. warning::
    Coverage is not yet supported when using fast mode.

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

    pytest --cov= --cov-branch ...

`pytest-cov <https://pytest-cov.readthedocs.io/en/latest/readme.html#usage>`_ is a wrapper around ``coverage.py`` for using with pytest; using it is recommended because it smooths out some quirks of using ``coverage.py`` with pytest.

Finally, ``coverage.py`` saves coverage data to a file named ``.coverage`` in the directory it is run in. To view the formatted coverage data, you typically want to use ``coverage report`` or ``coverage html``. See more options at https://coverage.readthedocs.io/en/latest/cmd.html.

Coverage is experimental and there may be odd corner cases! If so, please report them on github or in the ``#titanoboa-interpreter`` channel of the `Vyper discord <https://discord.gg/6tw7PTM7C2>`_.

Fuzzing Strategies
-----------------

Titanoboa offers custom `hypothesis <https://hypothesis.readthedocs.io/en/latest/quickstart.html>`_ strategies for testing. These can be used to generate EVM-compliant random inputs for tests.

Native Import Syntax
--------------------

Titanoboa supports the native Python import syntax for Vyper contracts. This means that you can import Vyper contracts in any Python script as if you were importing a Python module.

For example, if you have a contract ``contracts/Foo.vy``:

.. code-block:: vyper

    x: public(uint256)

    def __init__(x_initial: uint256):
        self.x = x_initial

You can import it in a Python script ``tests/bar.py`` like this


.. code-block:: python

    from contracts import Foo

    my_contract = Foo(42) # This will create a new instance of the contract

    my_contract.x() # Do anything with the contract as you normally would

Internally this will use the ``importlib`` module to load the file and create a ``ContractFactory``.


.. note::

    For this to work ``boa`` must be imported first.

    Due to limitations in the Python import system, only imports of the form ``import Foo`` or ``from <folder> import Foo`` will work and it is not possible to use ``import <folder>``.


Fast Mode
---------

Titanoboa has a fast mode that can be enabled by using ``boa.env.enable_fast_mode()``.

This mode performs a number of optimizations by patching some py-evm objects to speed up the execution of unit tests.

.. warning::
    Fast mode is experimental and may break other features of boa (like coverage).

ipython Vyper Cells
-------------------

Titanoboa supports ipython Vyper cells. This means that you can write Vyper code in a ipython/Jupyter Notebook environment and execute it as if it was a Python cell (the contract will be compiled instead, and a ``ContractFactory`` will be returned).

You can use Jupyter to execute titanoboa code in network mode from your browser using any wallet, using your wallet to sign transactions and call the RPC.
For a full example, please see `this example Jupyter notebook <../../examples/jupyter_browser_signer.ipynb>`_.

.. code-block:: python

    In [1]: import boa; boa.env.fork(url="<rpc server address>")

    In [2]: %load_ext boa.ipython

    In [3]: %%vyper Test
       ...: interface HasName:
       ...:     def name() -> String[32]: view
       ...:
       ...: @external
       ...: def get_name_of(addr: HasName) -> String[32]:
       ...:     return addr.name()
    Out[3]: <boa.vyper.contract.VyperDeployer at 0x7f3496187190>

    In [4]: c = Test.deploy()

    In [5]: c.get_name_of("0xD533a949740bb3306d119CC777fa900bA034cd52")
    Out[5]: 'Curve DAO Token'

Accessing non-public/external members
-------------------------------------

Titanoboa allows access to non-public/external members of a contract. This is useful for testing internal functions or variables without having to expose them to the outside world.

Given a vyper module ``foo.vy`` in the same folder as your python code:

.. code-block:: vyper

    x: uint256
    y: immutable(uint256)

    def __init__(y_initial: uint256):
        self.x = 42
        self.y = y_initial

    @internal
    @pure
    def _bar() -> uint256:
        return 111

``internal`` functions can be accessed by calling the function from the ``internal`` attribute of the contract.

.. code-block:: python

    import foo

    my_contract = foo(1234)

    my_contract.internal._bar() # Call the internal function _bar (returns 111)

Private storage variables can be accessed by calling the variable from the ``_storage`` attribute of the contract:

.. code-block:: python

    import foo

    my_contract = foo(1234)

    my_contract._storage.x.get() # Access the private storage variable x (returns 42)

Similarly private immutable variables can be accessed by calling the variable from the ``_immutable`` attribute of the contract:

.. code-block:: python

    import foo

    my_contract = foo(1234)

    my_contract._immutable.y # Access the private immutable variable y

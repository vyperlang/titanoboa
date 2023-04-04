Boa Test
========

Testing Functionality
----------------------



Gas Profiling Functionality
-----------------------

Titanoboa has native gas profiling tools that store and generate statistics upon calling a contract. When enabled,
gas costs are stored per call in global `boa.env._cached_call_profiles` and `boa.env._cached_line_profiles` dictionaries.
To enable gas profiling,

1. decorate tests with `@pytest.mark.profile`
2. run pytest with `--profile`, e.g. `pytest tests/unitary --profile`

To ignore profiling for specific tests, decorate the test with `@pytest.mark.ignore_profiling`.

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
    ┃    Contract ┃ Address                                    ┃ Computation ┃ Count ┃ Mean ┃ Median ┃ Stdev ┃ Min ┃ Max ┃
    ┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━┩
    │ FooContract │ 0x0000000000000000000000000000000000000069 │ foo         │ 1     │ 88   │ 88     │ 0     │ 88  │ 88  │
    └─────────────┴────────────────────────────────────────────┴─────────────┴───────┴──────┴────────┴───────┴─────┴─────┘


    ┏━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━┓
    ┃         Contract ┃ Computation                   ┃ Count ┃ Mean ┃ Median ┃ Stdev ┃ Min ┃ Max ┃
    ┡━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━┩
    │ FooContract(foo) │   4: def foo(a: uint256 = 0): │ 1     │ 73   │ 73     │ 0     │ 73  │ 73  │
    │                  │   5: x: uint256 = a           │ 1     │ 15   │ 15     │ 0     │ 15  │ 15  │
    └──────────────────┴───────────────────────────────┴───────┴──────┴────────┴───────┴─────┴─────┘

.. note::
    Note that if a specific fixture is called in two separate tests, pytest will re-instantiate it. Meaning, if a Contract
    is deployed in a fixture, calling the fixture on tests in two separate files can lead to two deployments of that Contract,
    and hence two separate addresses in the profile table.

.. warning::
    Profiling does not work with pytest-xdist plugin at the moment.

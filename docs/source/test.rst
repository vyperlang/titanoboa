Boa Test
========

Testing Functionality
----------------------



Gas Profiling Functionality
-----------------------

Titanoboa has native gas profiling tools that store and generate statistics upon calling a contract. When enabled,
gas costs are stored per call in global `boa.env._cached_call_profiles` and `boa.env._cached_line_profiles` dictionaries.
To enable, tests can be decorated with `@pytest.mark.profile`.

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

    ┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━┓
    ┃    Contract ┃ Address                                    ┃ Code ┃ Count ┃ Mean ┃ Median ┃ Stdev ┃ Min ┃ Max ┃
    ┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━┩
    │ FooContract │ 0x0000000000000000000000000000000000000066 │ foo  │ 1     │ 79   │ 79     │ 0     │ 79  │ 79  │
    └─────────────┴────────────────────────────────────────────┴──────┴───────┴──────┴────────┴───────┴─────┴─────┘

    ┏━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━┓
    ┃    Contract ┃ Code                           ┃ Count ┃ Mean ┃ Median ┃ Stdev ┃ Min ┃ Max ┃
    ┡━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━┩
    │ FooContract │    4: def foo(a: uint256 = 0): │ 1     │ 64   │ 64     │ 0     │ 64  │ 64  │
    │             │    5:     x: uint256 = a       │ 1     │ 15   │ 15     │ 0     │ 15  │ 15  │
    └─────────────┴────────────────────────────────┴───────┴──────┴────────┴───────┴─────┴─────┘

.. note::
    Note that if a specific fixture is called in two separate tests, pytest will re-instantiate it. Meaning, if a Contract
    is deployed in a fixture, calling the fixture on tests in two separate files will lead to two deployments of that Contract.
    This can lead to an over-populated profile table.

.. warning::
    Profiling does not work with pytest-xdist plugin at the moment.

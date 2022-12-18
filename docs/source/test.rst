Boa Test
========

Testing Functionality
----------------------



Profiling Functionality
-----------------------

Titanoboa has native call profiling tools that store and generate statistics for contract calls. If enabled,
call gas costs are stored in a global `boa.env._profiled_calls` dictionary. Subsequent calls from the same method
in a contract get appended to the appropriate `Contract.method` key. To enable, tests can be decorated with
`@pytest.mark.profile_calls`.

.. code-block:: python

    @pytest.mark.profile_calls
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

    --------------------------------------
                 Gas Profiles
    --------------------------------------

                    FooContract
    (0x0000000000000000000000000000000000000069)
    ┏━━━━━━━━┳━━━━━━┳━━━━━━━━┳━━━━━━━┳━━━━━┳━━━━━┓
    ┃ Method ┃ Mean ┃ Median ┃ Stdev ┃ Min ┃ Max ┃
    ┡━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━╇━━━━━╇━━━━━┩
    │    foo │ 137  │ 137    │ 0     │ 137 │ 137 │
    └────────┴──────┴────────┴───────┴─────┴─────┘

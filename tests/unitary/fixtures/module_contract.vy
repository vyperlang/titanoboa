# pragma version ^0.4.0
import module_lib

@external
@view
def fail():
    module_lib.throw()

import sys
import types


# take an exception instance, and strip frames in the target module
# from the traceback
def strip_internal_frames(exc, module_name=None):
    error_type, error, traceback = sys.exc_info()
    frame = traceback.tb_frame

    if module_name is None:
        # use the parent module of the module where the exception was raised
        module_name = frame.f_globals["__name__"].rsplit(".", 1)[0]

    # currently, module_name is always
    # `boa.contracts.vyper`, `boa.contracts.abi` or `boa.contracts`
    while frame.f_globals.get("__name__", "").startswith(module_name):
        frame = frame.f_back

    # kwargs incompatible with pypy here
    # tb_next=None, tb_frame=frame, tb_lasti=frame.f_lasti, tb_lineno=frame.f_lineno
    tb = types.TracebackType(None, frame, frame.f_lasti, frame.f_lineno)
    return error.with_traceback(tb)

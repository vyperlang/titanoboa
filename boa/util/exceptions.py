import sys
import types


# take an exception instance, and strip frames in the target module
# from the traceback
def strip_internal_frames(exc, package_name=None):
    error_type, error, traceback = sys.exc_info()
    frame = traceback.tb_frame

    if package_name is None:
        # use the parent module of the module where the exception was raised
        # currently, package_name is always `boa.contracts`
        package_name = frame.f_globals["__spec__"].parent

    # check with startswith because the package name may be a subpackage
    # currently, frame.f_globals["__spec__"].parent is always
    # `boa.contracts.vyper`, `boa.contracts.abi` or `boa.contracts`
    while frame.f_globals["__spec__"].parent.startswith(package_name):
        frame = frame.f_back

    # kwargs incompatible with pypy here
    # tb_next=None, tb_frame=frame, tb_lasti=frame.f_lasti, tb_lineno=frame.f_lineno
    tb = types.TracebackType(None, frame, frame.f_lasti, frame.f_lineno)
    return error.with_traceback(tb)

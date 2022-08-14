import sys
import types


# take an exception instance, and strip frames in the target module
# from the traceback
def strip_internal_frames(exc, module_name=None):
    ei = sys.exc_info()
    frame = ei[2].tb_frame

    if module_name is None:
        module_name = frame.f_globals["__name__"]

    while frame.f_globals.get("__name__", None) == module_name:
        frame = frame.f_back

    # kwargs incompatible with pypy here
    # tb_next=None, tb_frame=frame, tb_lasti=frame.f_lasti, tb_lineno=frame.f_lineno
    tb = types.TracebackType(None, frame, frame.f_lasti, frame.f_lineno)
    return ei[1].with_traceback(tb)

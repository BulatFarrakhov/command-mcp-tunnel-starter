"""Contain supervisor descendants in a kill-on-close Windows Job Object."""
import os


def contain_current_process():
    """Fail closed if Windows cannot attach the supervisor to a nested job.

    The non-inheritable handle remains open for the process lifetime. Windows
    closes it on any exit, including forced termination, killing descendants.
    """
    if os.name != "nt":
        return None
    import ctypes as c
    from ctypes import wintypes as w

    class Basic(c.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", c.c_longlong),
            ("PerJobUserTimeLimit", c.c_longlong),
            ("LimitFlags", w.DWORD),
            ("MinimumWorkingSetSize", c.c_size_t),
            ("MaximumWorkingSetSize", c.c_size_t),
            ("ActiveProcessLimit", w.DWORD),
            ("Affinity", c.c_size_t),
            ("PriorityClass", w.DWORD),
            ("SchedulingClass", w.DWORD),
        ]

    class Counters(c.Structure):
        _fields_ = [(name, c.c_ulonglong) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class Extended(c.Structure):
        _fields_ = [("BasicLimitInformation", Basic), ("IoInfo", Counters),
                    ("ProcessMemoryLimit", c.c_size_t), ("JobMemoryLimit", c.c_size_t),
                    ("PeakProcessMemoryUsed", c.c_size_t), ("PeakJobMemoryUsed", c.c_size_t)]

    k = c.WinDLL("kernel32", use_last_error=True)
    k.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]
    k.CreateJobObjectW.restype = w.HANDLE
    k.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
    k.SetInformationJobObject.restype = w.BOOL
    k.GetCurrentProcess.argtypes = []
    k.GetCurrentProcess.restype = w.HANDLE
    k.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
    k.AssignProcessToJobObject.restype = w.BOOL
    k.CloseHandle.argtypes = [w.HANDLE]
    k.CloseHandle.restype = w.BOOL

    handle = k.CreateJobObjectW(None, None)
    if not handle:
        raise c.WinError(c.get_last_error())
    info = Extended()
    info.BasicLimitInformation.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k.SetInformationJobObject(handle, 9, c.byref(info), c.sizeof(info)):
        error = c.get_last_error()
        k.CloseHandle(handle)
        raise c.WinError(error)
    if not k.AssignProcessToJobObject(handle, k.GetCurrentProcess()):
        error = c.get_last_error()
        k.CloseHandle(handle)
        raise c.WinError(error)
    # Do not close this handle while the supervisor is running.
    return handle

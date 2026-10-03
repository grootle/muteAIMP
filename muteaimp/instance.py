import ctypes

ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL(
    'kernel32',
    use_last_error=True
)

_kernel32.CreateMutexW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_bool,
    ctypes.c_wchar_p
]

_kernel32.CreateMutexW.restype = ctypes.c_void_p

_kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

_kernel32.CloseHandle.restype = ctypes.c_bool


class SingleInstance:
    """Prevent multiple instances of MuteAIMP on Windows"""

    def __init__(
        self,
        name: str = r'Local\MuteAIMP.SingleInstance'
    ):
        self.name = name
        self.handle = None

    def acquire(self) -> bool:
        """Return True if this process is the first instance"""

        self.handle = _kernel32.CreateMutexW(
            None,
            False,
            self.name
        )

        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())

        error = ctypes.get_last_error()

        if error == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(self.handle)
            self.handle = None
            return False

        return True

    def release(self):
        """Release the Windows mutex"""

        if self.handle is not None:
            _kernel32.CloseHandle(self.handle)
            self.handle = None

    def __del__(self):
        self.release()

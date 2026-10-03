import ctypes
import os
import sys
import time

from .logging_setup import LOG_FILE


def attach_console():
    """Attach to the parent console or allocate one for log viewing"""
    if os.name != 'nt':
        return

    if sys.stdout is not None and sys.stderr is not None:
        return

    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)

    kernel32.AttachConsole.argtypes = [ctypes.c_uint32]
    kernel32.AttachConsole.restype = ctypes.c_bool
    kernel32.AllocConsole.restype = ctypes.c_bool

    # ATTACH_PARENT_PROCESS
    attached = kernel32.AttachConsole(0xFFFFFFFF)

    if not attached:
        error = ctypes.get_last_error()

        # ERROR_ACCESS_DENIED can mean the process already
        # has a console, so try opening its console streams.
        if error != 5 and not kernel32.AllocConsole():
            raise ctypes.WinError(ctypes.get_last_error())

    # GUI scripts normally have no standard streams
    sys.stdout = open(
        'CONOUT$',
        'w',
        encoding='utf-8',
        errors='replace',
        buffering=1
    )

    sys.stderr = open(
        'CONOUT$',
        'w',
        encoding='utf-8',
        errors='replace',
        buffering=1
    )


def main():
    """Print existing logs and follow new entries until interrupted"""
    attach_console()

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    LOG_FILE.touch(exist_ok=True)

    print(f'MuteAIMP log: {LOG_FILE}')
    print('Showing previous logs and following new entries.')
    print('Press Ctrl+C to stop.\n')

    try:
        # Start at the beginning, then continue following appended lines
        with LOG_FILE.open(
            'r',
            encoding='utf-8',
            errors='replace'
        ) as log_file:
            while True:
                line = log_file.readline()

                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                else:
                    time.sleep(0.25)

    except KeyboardInterrupt:
        print('\nLog viewer stopped.')

    return 0

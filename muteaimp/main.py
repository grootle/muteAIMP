import ctypes
import sys

from .instance import SingleInstance


def set_windows_app_user_model_id():
    """Set a stable Windows identity for MuteAIMP"""
    if sys.platform != 'win32':
        return

    app_id = 'org.muteaimp.Desktop'

    shell32 = ctypes.WinDLL('shell32', use_last_error=True)

    set_app_id = (shell32.SetCurrentProcessExplicitAppUserModelID)
    set_app_id.argtypes = [ctypes.c_wchar_p]
    set_app_id.restype = ctypes.c_long

    result = set_app_id(app_id)

    if result != 0:
        raise OSError(
            f'Could not set Windows AppUserModelID: '
            f'HRESULT 0x{result & 0xFFFFFFFF:08X}'
        )


def main():
    """Application entry point"""

    # The log viewer is intentionally allowed to run while
    # the main MuteAIMP process is already running.
    if (
        len(sys.argv) > 1
        and sys.argv[1].casefold() == 'log'
    ):
        from .log_cli import main as log_main
        return log_main()

    instance = SingleInstance()

    if not instance.acquire():
        # Another muteAIMP instance is already running
        return 0

    try:
        from .logging_setup import APP_NAME, configure_logging

        logger = configure_logging(reset=True)
        logger.info(f'{APP_NAME} started')

        set_windows_app_user_model_id()

        from .ui import ApplicationController

        controller = ApplicationController()

        return controller.run()
    except Exception:
        logger.exception(f'{APP_NAME} terminated unexpectedly')
        raise
    finally:
        instance.release()


if __name__ == "__main__":
    sys.exit(main())

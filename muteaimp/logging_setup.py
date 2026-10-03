import logging
import os
from pathlib import Path

APP_NAME = 'MuteAIMP'
CONFIG_DIR = Path(os.getenv('LOCALAPPDATA', Path.home())) / APP_NAME
LOG_FILE = CONFIG_DIR / 'muteaimp.log'


def configure_logging(reset: bool = False):
    """
    Configure persistent file logging for the application.

    When reset=True, the previous log file is cleared and
    a fresh log starts for the current application run.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger('muteaimp')
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Prevent duplicate handlers if configure_logging()
    # is called more than once in the same process.
    existing_handler = next(
        (
            handler
            for handler in logger.handlers
            if getattr(
                handler,
                '_muteaimp_handler',
                False
            )
        ),
        None
    )

    if existing_handler is not None:
        return logger

    handler = logging.FileHandler(
        LOG_FILE,
        mode='w' if reset else 'a',
        encoding='utf-8',
        delay=False
    )

    handler.setFormatter(
        logging.Formatter(
            fmt=(
                '%(asctime)s '
                '[%(levelname)s] '
                '[%(threadName)s] '
                '%(name)s: %(message)s'
            ),
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    )

    handler._muteaimp_handler = True
    logger.addHandler(handler)

    return logger

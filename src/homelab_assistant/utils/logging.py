""" Custom logging class and helper functions to support custom log levels and setup. """
import functools
import logging
from enum import IntEnum
from typing import cast

from rich.logging import RichHandler

from homelab_assistant.utils.console import console


class LogLevels(IntEnum):
    """ List of permitted log level names, and their associated integer values. """

    # Default log levels Python's logging provides, defined for clarity.
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL

    # PRINT is used for informational statements that should always be shown to the user.
    # It is set to the highest level, such that it is never disabled.
    PRINT = 100


class CustomLogger(logging.Logger):
    """ Extension of standard logger class to introduce custom behaviour. """

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)
        logging.addLevelName(LogLevels.PRINT, LogLevels.PRINT.name)

    def print(self, msg: object, *args, **kwargs) -> None:
        """ Log 'msg % args' with severity 'PRINT'.

        To pass exception information, use the keyword argument `exc_info` with a True value.

        Example: ::
            logger.print("Houston, we have %s", "no problem, hello!", exc_info=1)
        """
        if self.isEnabledFor(LogLevels.PRINT):
            self._log(LogLevels.PRINT, msg, args, **kwargs)


def setup_logger(verbosity: int) -> None:
    """ Set up the root logger based on arguments to the main function. """
    # Set log levels based on verbosity specified by the user's command line inputs.
    log_levels = sorted([level.value for level in LogLevels])
    log_level = max(log_levels.index(logging.WARNING) - verbosity, 0)
    for name in logging.root.manager.loggerDict:
        # Set initial log levels only for self, avoiding clutter from 3rd party modules.
        if name.startswith("homelab_assistant"):
            logging.getLogger(name).setLevel(log_levels[0])

    # Set up the console output handler using Rich for coloured display.
    logging.getLogger().addHandler(
        RichHandler(
            console=console,
            show_time=False,
            enable_link_path=False,
            omit_repeated_times=False,
            rich_tracebacks=True,
            level=log_levels[log_level],
            markup=True,
        ),
    )


def getLogger(name: str | None = None) -> CustomLogger:  # noqa: N802 - Function name should be lowercase.
    """ Return a logger with the specified name, creating it if necessary.

    Acts as a wrapper function to the standard `logging.getLogger()` command to support type detection
    for the custom logging class, and allow use of custom logger functions without editor warnings.
    """
    return cast(CustomLogger, logging.getLogger(name))


# On import, set the default logger class to use the custom instance and override the print methods on CustomLogger.
logging.setLoggerClass(CustomLogger)
CustomLogger.print = functools.partialmethod(logging.Logger.log, LogLevels.PRINT)  # type: ignore[invalid-assignment]

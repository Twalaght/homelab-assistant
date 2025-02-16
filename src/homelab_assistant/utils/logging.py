""" Custom logging class and helper functions to support custom log levels and setup. """
import functools
import logging
from typing import cast

from rich.logging import RichHandler

from homelab_assistant.utils.console import console


class CustomLogger(logging.getLoggerClass()):
    """ Extension of standard logger class to introduce custom behaviour. """

    PRINT = 100

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        super().__init__(name, level)
        logging.addLevelName(self.PRINT, "PRINT")

    def print(self, msg: object, *args, **kwargs) -> None:
        """ Log 'msg % args' with severity 'PRINT'.

        To pass exception information, use the keyword argument `exc_info` with a True value.

        Example: ::
            logger.print("Houston, we have %s", "no problem, hello!", exc_info=1)
        """
        # This causes the current file (logging.py) to be reported as the origin of the log message.
        #
        # To fix this, at the bottom of this module we will override this method with a `functools.partialmethod`
        # version, AFTER the class has been defined.
        # As such, this function definition exists purely for documentation purposes.
        if self.isEnabledFor(self.PRINT):
            self._log(self.PRINT, msg, args, **kwargs)


def setup_logger(verbosity: int) -> None:
    """ Set up the root logger based on arguments to the main function. """
    log_levels = [
        # DEBUG is used for detailed information intended for use in debugging the program.
        logging.DEBUG,
        # INFO is used for informational statements about program execution, without any fine-grained details
        logging.INFO,
        # WARNING is used for notable alerts which do not otherwise interrupt execution.
        logging.WARNING,
        # ERROR is used for failures which are handled, OR interrupt program execution.
        # Note that `logger.exception()` calls will be logged under ERROR, just with exception information.
        logging.ERROR,
        # CRITICAL is used for failures which are NOT handled, and will interrupt program execution.
        logging.CRITICAL,
        # PRINT is used for informational statements that should always be shown to the user, but will be captured
        # by the log handler. Note that PRINT is set as the highest log level, so that it is never disabled.
        CustomLogger.PRINT,
    ]

    # Set log level based on verbosity specified by the user.
    log_level = max(log_levels.index(logging.WARNING) - verbosity, 0)
    for name in logging.root.manager.loggerDict:
        # Set logging level ONLY for our own output, to avoid cluttering
        # the logs with messages from imported 3rd party modules.
        if name.startswith("homelab_assistant"):
            logging.getLogger(name).setLevel(log_levels[0])

    # Set up the console output handler using Rich for coloured display.
    console_handler = RichHandler(
        console=console,
        show_time=False,
        enable_link_path=False,
        omit_repeated_times=False,
        rich_tracebacks=True,
        level=log_levels[log_level],
        markup=True,
    )
    logging.getLogger().addHandler(console_handler)


def getLogger(name: str | None = None) -> CustomLogger:
    """ Return a logger with the specified name, creating it if necessary.

    Acts as a wrapper function to the standard `logging.getLogger()` command to support type detection
    for the custom logging class, and allow use of custom logger functions without editor warnings.
    """
    return cast(CustomLogger, logging.getLogger(name))


# On import, set the default logger class to use the custom instance and override the print methods on CustomLogger.
logging.setLoggerClass(CustomLogger)
CustomLogger.print = functools.partialmethod(logging.Logger.log, CustomLogger.PRINT)

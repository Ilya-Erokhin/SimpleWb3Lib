from loguru import logger as loguru_logger
import sys


def setup_logger():
    """
    Setting up the logger via loguru library.

    Returns:
        loguru.Logger: Объект логера.
    """
    # Clean default loggers
    loguru_logger.remove()

    loguru_logger.add(
        sys.stdout,
        format="<green>{time:YYYY-MM-DD at HH:mm:ss}</green> \n"
               "| <level>{level}</level> | \n"
               "<cyan>{message}</cyan> \n",
        level="INFO",
        colorize=True
    )

    return loguru_logger


logger = setup_logger()

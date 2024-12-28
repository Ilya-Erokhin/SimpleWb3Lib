import asyncio
import random

from src.utils.logger import logger


async def sleep(sleep_from: int, sleep_to: int) -> None:
    """
    Sleep for a random time between sleep_from and sleep_to.

    :param sleep_from: The minimum number of seconds to sleep.
    :param sleep_to: The maximum number of seconds to sleep.
    :return: None
    """
    delay: int = random.randint(sleep_from, sleep_to)

    logger.info(f"💤 Sleep {delay} sec for the next request.")
    for _ in range(delay):
        await asyncio.sleep(1)

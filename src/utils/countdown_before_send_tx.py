import asyncio
from datetime import datetime
import sys


async def countdown_for_execute_time(target_time: str) -> None:
    """
    Countdown for execute time and print remaining time in minutes and seconds.

    :param target_time: Target time in format "dd.mm.yyyy HH:MM:SS".
    """
    target_datetime = datetime.strptime(target_time, "%d.%m.%Y %H:%M:%S")
    current_datetime = datetime.now()
    remaining_time = (target_datetime - current_datetime).total_seconds()

    while remaining_time > 0:
        minutes, seconds = divmod(int(remaining_time), 60)
        sys.stdout.write(f"\rRemaining time: {minutes} minutes {seconds} seconds")
        sys.stdout.flush()
        await asyncio.sleep(1)
        remaining_time -= 1

    sys.stdout.write("\rExecution time reached. Sending transaction...\n")
    sys.stdout.flush()

import asyncio
from typing import List

from eth_account import Account
from eth_typing import ChecksumAddress
from settings import MAX_RETRY_COUNT
import traceback
from functools import wraps

from src.utils.logger import logger
from src.utils.sleeping import sleep
from web3 import AsyncWeb3


def retry(func):
    """
    A decorator to retry an asynchronous function in case of an exception.

    :param func: Asynchronous function
    :return: Wrapper function
    """

    @wraps(func)
    async def wrapper(*args, **kwargs):
        retries = 0
        # Extract from_wallet_address from kwargs (if exists)
        from_wallet_address = kwargs.get('from_wallet_address', None)

        while retries <= MAX_RETRY_COUNT:
            try:
                logger.info(
                    f"🔄 Attempt {retries + 1}/{MAX_RETRY_COUNT + 1} -> for wallet address: {from_wallet_address}"
                )
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                logger.error(f"❌ Error on attempt {retries + 1}/{MAX_RETRY_COUNT + 1} | {e}")
                traceback.print_exc()
                retries += 1
                if retries > MAX_RETRY_COUNT:
                    logger.error("❌❌❌ Maximum retry attempts reached. Giving up.")
                    raise
                await sleep(sleep_from=1, sleep_to=3)  # Sleep for 1-3 seconds before retrying

    return wrapper


async def generate_addresses(private_keys: List[str]) -> List[ChecksumAddress]:
    """
    Asynchronous method to generate addresses from a list of private keys.

    :param private_keys: A list of private keys.
    :return: A list of addresses in checksum format.
    """

    async def fetch(private_key: str) -> ChecksumAddress:
        return AsyncWeb3.to_checksum_address(Account.from_key(private_key).address)

    fetch_tasks = [fetch(private_key) for private_key in private_keys]
    return await asyncio.gather(*fetch_tasks)


async def get_proxy(
        proxy_mapping: dict | None,
        private_key: str
) -> str | None:
    """
    Retrieves the proxy for a given private key.

    :param proxy_mapping: A dictionary containing -> private keys: proxies.
    :param private_key: The private key of the wallet.
    :return: Proxy string (login:password@ip:port) or None if proxies are not used.
    """
    if proxy_mapping:
        proxy: str | None = proxy_mapping.get(private_key)
        return proxy
    return None

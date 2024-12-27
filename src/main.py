import asyncio
from typing import List

from hexbytes import HexBytes

from src.models.models import TokenAmount, Networks
from src.client.client import Client
from src.tasks.woofi import WooFi


async def main():
    async with Client(network=Networks.Arbitrum) as client:
        woofi = WooFi(client=client)

        # tx_hashes: List[HexBytes] = await woofi.swap_eth_to_usdc(
        #     amount=TokenAmount(amount=0.00030, decimals=18),
        # )

        tx_hashes: List[HexBytes] = await woofi.swap_usdc_to_eth(
            amount=TokenAmount(amount=0.3, decimals=6),
            # execute_date_and_time="25.12.2024 19:48:00"  # dd.mm.yyyy HH:MM:SS
        )

        await woofi.client.verify_txs(tx_hashes=tx_hashes)


if __name__ == '__main__':
    asyncio.run(main())

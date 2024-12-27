import asyncio
from typing import List

from web3 import Web3
from hexbytes import HexBytes
from eth_typing import ChecksumAddress

from src.utils.logger import logger
from src.client.client import Client
from src.utils.utils import read_json
from src.config.config import WOOFI_ABI
from src.models.models import TokenAmount
from web3.contract import AsyncContract
from web3.types import TContractEvent


class WooFi:
    eth_address = Web3.to_checksum_address(
        '0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE'
    )
    usdc_address = Web3.to_checksum_address(
        '0xaf88d065e77c8cC2239327C5EDb3A432268e5831'
    )

    # Where the transaction goes
    router_abi: list | dict = read_json(WOOFI_ABI)
    router_address: ChecksumAddress = Web3.to_checksum_address('0x4c4AF8DBc524681930a27b2F1Af5bcC8062E6fB7')

    def __init__(self, client: Client):
        self.client = client

    ##################################################################################################################
    async def swap_eth_to_usdc(
            self,
            slippage: float = 1,
            amount: TokenAmount | None = None,
            execute_date_and_time: str | None = None,
    ) -> List[HexBytes]:
        """
        Swap ETH to USDC.

        :param amount: Amount of USDC to swap
        :param slippage: Slippage in percentage
        :param execute_date_and_time: Time of transaction execution
        :return: List of hex bytes
        """
        eth_price: float = await self.client.get_token_price(token='ETH')
        contract: AsyncContract = await self.client.get_contract(
            contract_address=self.router_address,
            abi=self.router_abi
        )
        from_addresses: List[ChecksumAddress] = await self.client.generate_addresses(self.client.private_keys)

        min_to_amount = TokenAmount(
            amount=eth_price * float(amount.Ether) * (1 - slippage / 100),
            decimals=6
        )

        # Sending the prepared transaction
        transaction_tasks = [
            self.client.send_async_txn_with_prepared_data(
                to=self.router_address,
                from_wallet_address=address,
                data=contract.encode_abi(
                    abi_element_identifier='swap',
                    args=(
                        self.eth_address,
                        self.usdc_address,
                        amount.Wei,
                        min_to_amount.Wei,
                        address,
                        address,
                    )
                ),
                value=amount.Wei,
                execute_date_and_time=execute_date_and_time,
            )
            for address in from_addresses
        ]
        transaction_hashes = await asyncio.gather(*transaction_tasks, return_exceptions=True)

        return transaction_hashes

    async def swap_usdc_to_eth(
            self,
            slippage: float = 1,
            amount: TokenAmount | None = None,
            execute_date_and_time: str | None = None,
    ) -> List[HexBytes]:
        """
        Swap USDC to ETH.

        :param slippage: Slippage in percentage
        :param execute_date_and_time: Time of transaction execution
        :param amount: Amount of USDC to swap
        :return: List of transaction hashes
        """
        eth_price: float = await self.client.get_token_price(token='ETH')
        contract: AsyncContract = await self.client.get_contract(
            contract_address=self.router_address,
            abi=self.router_abi
        )
        from_addresses: List[ChecksumAddress] = await self.client.generate_addresses(
            private_keys=self.client.private_keys
        )
        balances: List[TokenAmount] = await self.client.balances_of(
            contract_token_address=self.usdc_address
        )
        allowances: List[TokenAmount] = await self.client.get_allowances(
            contract_token_address=self.usdc_address,
            spender_address=self.router_address
        )

        if not amount:
            for balance in balances:
                amount = TokenAmount(
                    amount=balance,
                    decimals=6,
                    wei=True
                )

        # Step 1: Approval for all addresses
        approve_tasks = [
            self.client.approve(
                allowance=allowance,
                wallet_address=address,
                balance=balance,
                contract_token_address=self.usdc_address,
                spender_address=self.router_address,
                amount_to_approve=amount
            ) for address, balance, allowance in zip(from_addresses, balances, allowances)
        ]
        await asyncio.gather(*approve_tasks, return_exceptions=True)

        min_to_amount = TokenAmount(
            amount=float(amount.Ether) / eth_price * (1 - slippage / 100),
        )

        # Step 2: Sending the prepared transaction
        transaction_tasks = [
            self.client.send_async_txn_with_prepared_data(
                to=self.router_address,
                from_wallet_address=address,
                data=contract.encode_abi(
                    abi_element_identifier='swap',
                    args=(
                        self.usdc_address,  # fromToken
                        self.eth_address,  # toToken
                        amount.Wei,  # fromAmount - How much USDC we want to swap
                        min_to_amount.Wei,  # minToAmount - Minimum amount of ETH to receive (in wei)
                        address,  # to
                        address  # rebateTo
                    )
                ),
                execute_date_and_time=execute_date_and_time,
            ) for address in from_addresses
        ]
        transaction_hashes = await asyncio.gather(*transaction_tasks, return_exceptions=True)

        return transaction_hashes

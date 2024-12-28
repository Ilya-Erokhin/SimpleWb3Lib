import asyncio
import inspect
import itertools

import aiohttp
from settings import USE_PROXY, INCREASE_GAS
from src.utils.helpers import retry, generate_addresses, get_proxy

from web3 import AsyncWeb3
from hexbytes import HexBytes
from web3.eth import AsyncEth
from eth_account import Account
from typing import List, Tuple, Dict, Any
from eth_typing import ChecksumAddress
from web3.contract import AsyncContract
from eth_account.datastructures import SignedTransaction
from src.utils.countdown_before_send_tx import countdown_for_execute_time

from src.utils.logger import logger
from src.utils.utils import read_json
from src.utils.load_proxies import load_proxies
from src.models.models import Network, TokenAmount
from src.utils.load_private_keys import load_private_keys
from src.config.config import TOKEN_ABI, PRIVATE_KEYS_FILE, PROXIES_FILE


class Client:
    default_token_abi: dict = read_json(TOKEN_ABI)

    def __init__(self, network: Network) -> None:
        """
        Initializes the Client class for interacting with the specified blockchain network.
        """
        self.network = network
        self.private_keys: list = load_private_keys(file_path=PRIVATE_KEYS_FILE)
        self.proxies: itertools.cycle = load_proxies(proxies_file=PROXIES_FILE)
        self.proxy_mapping: dict | None = (
            dict(zip(self.private_keys, self.proxies))
            if USE_PROXY
            else None
        )
        if USE_PROXY:
            proxy_cycle = itertools.cycle(self.proxies)
            self.proxy_mapping: dict | None = {
                private_key: next(proxy_cycle) for private_key in self.private_keys
            }
        self.async_w3 = AsyncWeb3(
            provider=AsyncWeb3.AsyncHTTPProvider(
                endpoint_uri=self.network.rpc),
            modules={'eth': (AsyncEth,)},
            middleware=[]
        )
        self.session: aiohttp.ClientSession = None
        self.logged_addresses = set()
        self.semaphore = asyncio.Semaphore(10)

    async def __aenter__(self):
        """
        Asynchronous context manager enter method.
        Initializes the aiohttp ClientSession and associates it with the AsyncWeb3 provider.
        """
        if self.session is None:
            try:
                logger.debug("🛠️ Attempting to create a new aiohttp ClientSession.")
                self.session = aiohttp.ClientSession()
                await self.async_w3.provider.cache_async_session(self.session)
                logger.info(f"🚀 Client session started for network: {self.network.name.capitalize()}")

                if self.proxy_mapping:
                    for private_key, proxy in self.proxy_mapping.items():
                        address: ChecksumAddress = AsyncWeb3.to_checksum_address(
                            Account.from_key(private_key).address
                        )
                        logger.info(f"📝 Wallet address: {address} -> Proxy: {proxy}")
                else:
                    logger.info("📝 No proxies configured for any wallets.")

            except Exception as e:
                logger.error(
                    f"❌ Failed to create ClientSession for network: "
                    f"{self.network.name}: \n{e}")
                raise
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        """
        Asynchronous context manager exit method.
        Closes the aiohttp ClientSession to clean up resources.
        """
        try:
            if self.session:
                logger.debug("Closing aiohttp ClientSession.")
                await self.session.close()
                logger.info("✅ Client session closed successfully.")
                self.session = None  # To avoid reclosing
            else:
                logger.warning("⚠️ Attempted to close ClientSession, but it was already None. ⚠️")
        except Exception as e:
            logger.error(f"❌ Error occurred while closing ClientSession: \n{e}")
            raise

    def get_contract(
            self,
            contract_address: str,
            abi: dict | None = None
    ) -> AsyncContract:
        """
        Retrieves the contract object for the specified contract address.

        :param abi: The ABI of the contract.
        :param contract_address: The contract address.
        :return: The contract object.
        """
        if abi is None:
            abi: dict = Client.default_token_abi
        return self.async_w3.eth.contract(
            address=AsyncWeb3.to_checksum_address(contract_address),
            abi=abi
        )

    async def fetch_data(
            self,
            contract,
            func_name: str,
            private_keys: List[str],
            *args
    ) -> List[Tuple[ChecksumAddress, int]]:
        """
        Generic method for fetching data from a contract.

        :param contract: The contract to interact with.
        :param func_name: The name of the contract function (balanceOf or allowance).
        :param private_keys: A list of private keys to derive addresses.
        :param args: Arguments to be passed to the contract function.
        :return: A list of tuples containing WALLET ADDRESS and the CONTRACT FUNCTION CALL RESULT
        """
        # Create the session once for all requests
        async with aiohttp.ClientSession() as session:
            async def fetch(private_key: str) -> Tuple[ChecksumAddress, int]:
                address = AsyncWeb3.to_checksum_address(Account.from_key(private_key=private_key).address)
                func = getattr(contract.functions, func_name)

                # Get the proxy for this wallet
                proxy: str | None = await get_proxy(
                    proxy_mapping=self.proxy_mapping,
                    private_key=private_key
                )

                if proxy:
                    # Determine the protocol based on the proxy (you could store this information in a dict or file)
                    async with session.get(self.network.rpc, proxy=f"http://{proxy}"):
                        result = await func(address, *args).call()
                else:
                    # If no proxy, simply perform the request directly
                    async with session.get(self.network.rpc):
                        result = await func(address, *args).call()
                return address, result

            # Create tasks for all private keys
            fetch_tasks = [fetch(private_key) for private_key in private_keys]
            return await asyncio.gather(*fetch_tasks)

    ############################################# READ Functions ######################################################

    async def get_decimals(self, contract_token_address: str) -> int:
        """
        Retrieves the number of decimal places for the token.
        :param contract_token_address: The token contract address (BASE - NOT PROXY).
        """
        contract: AsyncContract = self.get_contract(contract_address=contract_token_address)
        decimals: int = await contract.functions.decimals().call()
        return decimals

    async def balances_of(
            self,
            contract_token_address: str,
            wei: bool = True,
            log: bool = True,
    ) -> List[TokenAmount]:
        """
        Retrieve the balance of tokens at the specified address.

        :param contract_token_address: The token contract address (BASE - NOT PROXY).
        :param wei: Whether to return in WEI or not.
        :param log: Whether to log balance information.
        :return: A list of TokenAmount objects with balance and decimal values.
        """
        contract: AsyncContract = self.get_contract(contract_address=contract_token_address)

        decimals: int = await self.get_decimals(contract_token_address=contract_token_address)
        balances: List[TokenAmount] = []

        results: List[Tuple[ChecksumAddress, int]] = await self.fetch_data(
            contract=contract,
            func_name='balanceOf',
            private_keys=self.private_keys
        )

        for address, balance in results:
            formatted_balance: float = balance / (10 ** decimals)

            if address not in self.logged_addresses and log:
                logger.info(
                    f'💰 Log from function: "{inspect.currentframe().f_code.co_name}" \n'
                    f'Balance of wallet address: {address} is {formatted_balance:,.5f} USD'
                )
                token_amount = TokenAmount(
                    amount=balance,
                    decimals=decimals,
                    wei=wei
                )
                balances.append(token_amount)
                self.logged_addresses.add(address)
        return balances

    async def get_allowances(
            self,
            contract_token_address: str,
            spender_address: str
    ) -> List[TokenAmount]:
        """
        Retrieve information about the allowance for a third party to transfer tokens.
        Indicates how much the third party can spend.

        :param contract_token_address: The token contract address (BASE - NOT PROXY).
        :param spender_address: The address of the spender.
        :return: A list of TokenAmount objects with allowances and decimal values.
        """
        contract: AsyncContract = self.get_contract(contract_address=contract_token_address)

        results: List[Tuple[ChecksumAddress, int]] = await self.fetch_data(
            contract,
            'allowance',
            self.private_keys,
            spender_address
        )

        allowances = []
        for address, allowance in results:
            allowances.append(allowance)
            logger.info(
                f'Log from function: "{inspect.currentframe().f_code.co_name}" \n'
                f'Allowance for address: {address} to spender {spender_address} is {allowance} WEI'
            )
        return allowances

    ############################################# WRITE Functions ######################################################

    @staticmethod
    async def get_max_priority_fee_per_gas(
            w3: AsyncWeb3,
            block: dict
    ) -> int:
        """
        Get the maximum additional gas fee (or "tip") for transactions in a given block.

        :param w3: AsyncWeb3 object.
        :param block: A dictionary containing information about the block.
        :return: Maximum additional gas commission in WEI.
        """
        block_number: int = block["number"]
        latest_block_transaction_count: int = await w3.eth.get_block_transaction_count(block_number)
        max_priority_fee_per_gas_lst: list = []

        tasks = [
            w3.eth.get_transaction_by_block(block_number, transaction_index)
            for transaction_index in range(latest_block_transaction_count)
        ]

        transactions = await asyncio.gather(*tasks)

        for transaction in transactions:
            if transaction and "maxPriorityFeePerGas" in transaction:
                max_priority_fee_per_gas_lst.append(transaction["maxPriorityFeePerGas"])

        # If no data is available, return the standard maximum priority fee
        if not max_priority_fee_per_gas_lst:
            max_priority_fee_per_gas_wei: int = await w3.eth.max_priority_fee
        else:
            max_priority_fee_per_gas_lst.sort()
            max_priority_fee_per_gas_wei: int = max_priority_fee_per_gas_lst[len(max_priority_fee_per_gas_lst) // 2]

        return max_priority_fee_per_gas_wei

    async def prepare_data_for_send_async_tx(
            self,
            from_wallet_address: ChecksumAddress,
            to: str,
            data: str = None,
            increase_gas: float = INCREASE_GAS,
            value: int = None,
            max_priority_fee_per_gas: int = None,
            max_fee_per_gas: int = None,
    ) -> Dict[str, SignedTransaction | Dict[str, Any]]:
        """
        Prepares transaction data for sending to the blockchain.

        :param from_wallet_address: Wallet address.
        :param to: Recipient address.
        :param data: Transaction data (if applicable).
        :param increase_gas: The gas increase factor for the transaction. (1.1 - 10% increase)
        :param value: Amount ETH in Wei sent with the transaction (if applicable).
        :param max_priority_fee_per_gas: Maximum additional gas fee.
        :param max_fee_per_gas: Maximum gas fee.
        :return: Prepared transaction parameters and signed transaction.
        """
        base_log: str = (
            f'Log from function: "{inspect.currentframe().f_code.co_name}" \n'
            f'For wallet address | {from_wallet_address} \n'
        )

        tx_params: dict = {
            'chainId': await self.async_w3.eth.chain_id,
            'nonce': await self.async_w3.eth.get_transaction_count(account=from_wallet_address),
            'from': from_wallet_address,
            'to': AsyncWeb3.to_checksum_address(value=to),
        }

        if data:
            tx_params['data'] = data

        if self.network.eip1559_tx:
            last_block: dict = await self.async_w3.eth.get_block(block_identifier='latest')

            max_priority_fee_per_gas = max_priority_fee_per_gas or await Client.get_max_priority_fee_per_gas(
                w3=self.async_w3,
                block=last_block,
            )

            base_fee = int(last_block['baseFeePerGas'] * increase_gas)
            max_fee_per_gas = max_fee_per_gas or base_fee + max_priority_fee_per_gas

            tx_params.update({
                'maxPriorityFeePerGas': max_priority_fee_per_gas,
                'maxFeePerGas': max_fee_per_gas,
            })
        else:
            tx_params['gasPrice'] = await self.async_w3.eth.gas_price

        if value:
            tx_params['value'] = value

        try:
            tx_params['gas'] = int(
                await self.async_w3.eth.estimate_gas(transaction=tx_params) * increase_gas)
        except Exception as err:
            logger.error(
                f'❌ {base_log}Transaction FAILED during "gas" parameter calculation! \n'
                f'With transaction params: \n{tx_params} \n'
                f'Error message: {err} \n'
            )

        logger.info(
            f'⏳ {base_log}Final tx_params is: \n{tx_params} \n'
            f'Calculation of parameters is COMPLETED!'
        )

        private_key = next(
            (key for key in self.private_keys if Account.from_key(key).address == from_wallet_address),
            None
        )

        if private_key is None:
            raise ValueError(f"❌ Private key for address {from_wallet_address} not found.")

        signed_txn: SignedTransaction = self.async_w3.eth.account.sign_transaction(
            transaction_dict=tx_params,
            private_key=private_key
        )

        return {
            'tx_params': tx_params,
            'signed_txn': signed_txn
        }

    @retry
    async def send_row_async_transaction(
            self,
            signed_txn: SignedTransaction,
            tx_params: dict,
            from_wallet_address: ChecksumAddress = None,
    ) -> List[HexBytes]:
        """
        Sends a signed transaction to the blockchain.

        :param from_wallet_address: Wallet address.
        :param signed_txn: The signed transaction.
        :param tx_params: Transaction parameters.
        :return: List of transaction hashes.
        """
        base_log: str = (
            f'Log from function: "{inspect.currentframe().f_code.co_name}" \n'
            f'For wallet address (from) | {from_wallet_address} \n'
            f'For spender address (to) | {tx_params["to"]} \n'
        )

        transaction_hashes: List[HexBytes] = []
        ########################################################## TODO: Нужен ли тут semaphore?
        try:
            tx_hash: HexBytes = await self.async_w3.eth.send_raw_transaction(
                transaction=signed_txn.raw_transaction
            )
            logger.success(
                f'✅ {base_log}SUCCESSFUL Transaction! \n'
                f'With transaction params: \n{tx_params} \n'
            )
            transaction_hashes.append(tx_hash)
        except Exception as e:
            logger.error(
                f'❌ {base_log}Transaction FAILED: \n'
                f'Transaction parameters: {tx_params}\n'
                f'Signed transaction: {signed_txn.raw_transaction.hex()}\n'
                f'An Error: {e}'
            )
            raise

        return transaction_hashes

    async def send_async_txn_with_prepared_data(
            self,
            to: str,
            increase_gas: float = INCREASE_GAS,
            from_wallet_address: ChecksumAddress = None,
            data: str = None,
            value: int = None,
            max_priority_fee_per_gas: int = None,
            max_fee_per_gas: int = None,
            execute_date_and_time: str | None = None,
    ) -> List[HexBytes]:
        """
        Sends a transaction asynchronously with prepared data.

        :param to: Recipient address.
        :param increase_gas: The gas increase factor for the transaction.
            (1.1 - 10% increase)
        :param from_wallet_address: Wallet address.
        :param data: Transaction data (if applicable).
        :param value: Amount ETH in Wei sent with the transaction (if applicable).
        :param max_priority_fee_per_gas: Maximum additional gas fee.
        :param max_fee_per_gas: Maximum gas fee.
        :param execute_date_and_time: Scheduled time for transaction execution.
        :return: List of transaction hashes.
        """
        # Prepare the transaction data
        prepared_data: Dict[str, SignedTransaction | Dict[str, Any]] = await self.prepare_data_for_send_async_tx(
            from_wallet_address=from_wallet_address,
            to=to,
            data=data,
            increase_gas=increase_gas,
            value=value,
            max_priority_fee_per_gas=max_priority_fee_per_gas,
            max_fee_per_gas=max_fee_per_gas,
        )

        # If execution time is set, wait until the scheduled time
        if execute_date_and_time:
            await countdown_for_execute_time(execute_date_and_time)

        # Send the prepared transaction
        transaction_hashes: List[HexBytes] = await self.send_row_async_transaction(
            signed_txn=prepared_data['signed_txn'],
            tx_params=prepared_data['tx_params'],
            from_wallet_address=from_wallet_address,
        )

        return transaction_hashes

    async def verify_txs(
            self,
            tx_hashes: List[HexBytes],
            fn_log_name: str | None = None
    ) -> bool:
        """
        Check if the transaction was successful.

        :param fn_log_name: Name of the function for which verify_single_tx is called
        :param tx_hashes: List of transaction hashes for verifying.
        :return: True - if all transactions are successful, otherwise - False
        """
        base_log = (
            f'Log from function: "{inspect.currentframe().f_code.co_name}"\n'
        )
        from_addresses: List[ChecksumAddress] = await generate_addresses(
            private_keys=self.private_keys
        )

        all_tx_hashes: List[HexBytes] = (
            [tx_hash for sublist in tx_hashes for tx_hash in sublist] if any(
                isinstance(i, list) for i in tx_hashes) else tx_hashes
        )

        retry_counts: Dict[HexBytes, int] = {tx_hash: 0 for tx_hash in all_tx_hashes}

        async def verify_single_tx(tx_hash: HexBytes, address: ChecksumAddress) -> bool:
            current_log = base_log + f'Wallet Address: {address} \n'
            if fn_log_name:
                current_log += f'For {fn_log_name} function \n'

            tx_hash_str: str | HexBytes = tx_hash.hex() if isinstance(tx_hash, HexBytes) else tx_hash
            attempts = 5
            while retry_counts[tx_hash] < attempts:
                try:
                    async with self.semaphore:
                        data: dict = await self.async_w3.eth.wait_for_transaction_receipt(
                            transaction_hash=tx_hash,
                            timeout=200
                        )

                    if 'status' in data:
                        if data['status'] == 1:
                            logger.success(
                                f'✅ {current_log}Transaction was SUCCESSFUL! \n'
                                f'Transaction hash: {tx_hash_str} \n')
                            return True
                        else:
                            logger.error(
                                f'❌ {current_log}Transaction FAILED!!! \n'
                                f'Transaction hash: {tx_hash_str} \n'
                                f'Received status: {data["status"]} \n')
                            return False
                    else:
                        logger.warning(
                            f'⚠️{current_log}No status found in transaction receipt! \n'
                            f'Data: {data}⚠️\n')
                        return False

                except asyncio.TimeoutError:
                    logger.error(
                        f'❌ {current_log}Timeout error \n'
                        f'Transaction hash: {tx_hash_str} \n'
                        f'Exceeded timeout while waiting for transaction receipt. \n')
                    return False
                except Exception as err:
                    logger.error(
                        f'❌ {current_log}UNEXPECTED ERROR \n'
                        f'Transaction hash: {tx_hash_str} \n'
                        f'Error type: {type(err).__name__} \n'
                        f'Error message: {err} \n')
                    return False
            return False

        verify_tasks = [
            verify_single_tx(tx_hash, address) for tx_hash in all_tx_hashes for address in from_addresses
        ]
        results = await asyncio.gather(*verify_tasks)
        return all(results)

    async def approve(
            self,
            allowance: TokenAmount,
            wallet_address: ChecksumAddress,
            balance: TokenAmount,
            contract_token_address: str,
            spender_address: str,
            amount_to_approve: TokenAmount | None = None
    ) -> bool:
        """
        Approve the specified amount of tokens for the spender address.

        :param allowance: Current allowance for the wallet address and spender.
        :param wallet_address: The address of the wallet that is approving the tokens.
        :param balance: The balance of tokens in the wallet.
        :param contract_token_address: The address of the token contract.
        :param spender_address: The address of the spender that will be approved to spend the tokens.
        :param amount_to_approve: The amount of tokens to approve. If None, the entire balance is approved.
        :return: True if the approval transaction was successful, False otherwise.
        """
        contract: AsyncContract = self.get_contract(contract_address=contract_token_address)
        decimals: int = await self.get_decimals(contract_token_address=contract_token_address)

        base_log = (
            f'Log from function: "{inspect.currentframe().f_code.co_name}" \n'
            f'Wallet Address | {wallet_address} \n'
            f'Start approve token: {contract_token_address} \n'
            f'For spender address: {spender_address} \n'
        )

        if balance.Wei <= 0:
            logger.info(
                f"{base_log} Skip approve, balance of wallet is 0 :(( \n"
                f"Executing approve for the next wallet..."
            )
            return False

        # If the amount is not specified or is > balance, approve the ENTIRE BALANCE
        if not amount_to_approve or amount_to_approve.Wei > balance.Wei:
            amount_to_approve: TokenAmount = balance

        approved = TokenAmount(
            amount=allowance,
            decimals=decimals,
            wei=True
        )

        if amount_to_approve.Wei <= approved.Wei:
            logger.info(
                f"{base_log}\n"
                f"Current wallet ALREADY HAS APPROVED WITH: {approved.Ether} USD\n"
            )
            return True

        approve_tx_hashes: List[HexBytes] = await self.send_async_txn_with_prepared_data(
            to=contract_token_address,
            from_wallet_address=wallet_address,
            data=contract.encode_abi(
                'approve',
                args=(spender_address, amount_to_approve.Wei)
            )
        )
        single_approve_tx_hash: str = f"{', '.join([tx_hash.hex() for tx_hash in approve_tx_hashes])}"

        verification_result: bool = await self.verify_txs(
            tx_hashes=approve_tx_hashes,
            fn_log_name='approve'
        )
        log_message = (
            f"{base_log}Transaction "
            f"{'SUCCESSFULLY PASSED' if verification_result else 'FAILED'} "
            f"VERIFICATION in verify_txs \n"
            f"Approve transaction hash: {single_approve_tx_hash}"
        )
        if verification_result:
            logger.success(
                "✅" +
                log_message +
                f"\nFINAL SUCCESSFUL APPROVE is: {amount_to_approve.Ether} USD"
            )
        else:
            logger.error("❌" + log_message)
        return verification_result

    async def get_token_price(self, token: str = 'ETH') -> float | None:
        """
        Get the current price of the specified token against USDT.

        :param token: The symbol of the token (e.g., 'ETH').
        :return: The current price of the token or None if an error occurs.
        """
        token = token.upper()
        url = f'https://api.binance.com/api/v3/depth?limit=1&symbol={token}USDT'
        base_log: str = f'Log from function: "{inspect.currentframe().f_code.co_name}" \n'

        try:
            async with self.session.get(url) as response:
                response_data = await response.json()
                error_details: str = (
                    f'❌ Status code: {response.status} \n'
                    f'Error occurred: \n'
                    f'JSON response: {response_data} \n'
                )
                if response.status != 200:
                    logger.error("❌" + base_log + error_details)
                    return None
                if 'asks' not in response_data:
                    logger.error(f"❌ {base_log}No 'asks' found in response \n{error_details}")
                    return None
                token_price = float(response_data['asks'][0][0])
                logger.success(f"✅ {base_log}Current {token} price: {token_price}")
                return token_price
        except Exception as e:
            logger.error(f"❌ {base_log}Unexpected error occurred: {e}")
            return None

    # async def check_claim_status(
    #         self,
    #         wallet_address: ChecksumAddress,
    #         contract_token_address: str,
    #         abi: dict,
    # ):
    #     """
    #     Check the status of a claim.
    #
    #     :param wallet_address: The wallet address.
    #     :param contract_token_address: The token contract address.
    #     :param abi: The ABI of the contract.
    #     :return:
    #     """
    #     base_log = (
    #         f'Log from function: "{inspect.currentframe().f_code.co_name}" \n'
    #     )
    #     contract: AsyncContract = self.get_contract(
    #         contract_address=contract_token_address,
    #         abi=abi
    #     )
    #
    #     claim_idx = 0  # TODO: Count the number of claims from contract
    #
    #     claimable = await contract.functions.isClaimable().call()
    #     is_claimed = contract.functions.isClaimed(wallet_address, claim_idx).call()

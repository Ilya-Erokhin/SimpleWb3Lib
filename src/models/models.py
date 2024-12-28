import requests

from decimal import Decimal
from web3 import AsyncWeb3
from web3.eth import AsyncEth


class TokenAmount:
    """
    Class for automatic conversion of tokens between different units (e.g., WEI and ETH).

    Attributes:
    ----------
    Wei : int
        Amount in WEI.
    Ether : Decimal
        Amount in main units (e.g., ETH, USDC ...).
    decimals : int
        Number of decimal places for the token.
    """

    Wei: int
    Ether: Decimal
    decimals: int

    def __init__(
            self,
            amount: int | float | str | Decimal,
            decimals: int = 18,
            wei: bool = False,
    ) -> None:
        """
        Converts minimal units of a token to main units or vice versa.

        Parameters:
        ----------
        amount : int | float | str | Decimal
            Amount of tokens for conversion.
        decimals : int, optional
            Number of decimal places for the token (default is 18 for ETH).
        wei : bool, optional
            If True: Returns the amount in MINIMAL UNITS - WEI,
            If False: Returns the amount in MAIN UNITS (e.g., ETH) (default is False).
        usd : bool, optional
            If True: Interprets the amount as USD and converts to main units (e.g., ETH) (default is False).
        """
        match wei:
            case True:  # If we want to get the final value in MINIMAL units - WEI
                self.Wei: int = int(amount)
                self.Ether: Decimal = Decimal(str(amount)) / 10 ** decimals
            case False:  # If we want to get the final value in MAIN units (e.g., ETH)
                self.Wei: int = int(Decimal(str(amount)) * 10 ** decimals)
                self.Ether: Decimal = Decimal(str(amount))

        self.decimals = decimals

    @staticmethod
    def get_eth_to_usd_price() -> Decimal:
        """
        Get the current price of ETH in USD.

        Returns:
        -------
        Decimal
            Current price of ETH in USD.
        """
        response = requests.get('https://api.coinbase.com/v2/prices/ETH-USD/spot')
        data = response.json()
        return Decimal(data['data']['amount'])

    def __str__(self) -> str:
        return (
            f"\n"
            f"TokenAmount( \n"
            f"   Wei: {self.Wei}, \n"
            f"   Ether: {self.Ether}, \n"
            f"   Decimals: {self.decimals}"
            f"\n)"
        )


class Network:
    """
    Class for representing blockchain networks.

    Attributes:
        name (str): Name of the network.
        rpc (str): URL of the network's RPC node.
        chain_id (int): Chain identifier.
        eip1559_tx (bool): Whether the network supports EIP-1559 transactions.
        coin_symbol (str): Symbol of the network's native coin.
        explorer (str): URL of the blockchain explorer.
        decimals (int): Number of decimal places for the native coin (default is 18).

    Methods:
        __str__(): Returns a string representation of the object.
    """

    def __init__(
            self,
            name: str,
            rpc: str,
            chain_id: int,
            eip1559_tx: bool,
            coin_symbol: str,
            explorer: str,
            decimals: int = 18,
    ) -> None:
        self.name = name
        self.rpc = rpc
        self.chain_id = chain_id
        self.eip1559_tx = eip1559_tx
        self.coin_symbol = coin_symbol
        self.decimals = decimals
        self.explorer = explorer

        # If the chain identifier is not provided, try to get it via RPC
        if not self.chain_id:
            try:
                self.chain_id: int = AsyncWeb3(
                    provider=AsyncWeb3.AsyncHTTPProvider(
                        endpoint_uri=self.rpc),
                    modules={'eth': (AsyncEth,)},
                    middleware=[]
                ).eth.chain_id
            except Exception as err:
                raise ValueError(f"❌ Error getting chain identifier: \n {err}")

        # If the coin symbol is NOT PROVIDED, try to get it via API
        if not self.coin_symbol:
            try:
                resp = requests.get("https://chainid.network/chains.json").json()
                for network in resp:
                    if network["chainId"] == self.chain_id:
                        self.coin_symbol: str = network["nativeCurrency"]["symbol"]
                        break
            except Exception as err:
                raise ValueError(f"❌ Error getting coin symbol: \n {err}")

        if self.coin_symbol:
            self.coin_symbol = self.coin_symbol.upper()

    def __str__(self) -> str:
        """
        Returns a string representation of the Network object.

        Returns:
            str: A string representing the object, including its main attributes.
        """
        return (
            f"Network( \n"
            f"  name={self.name}, \n"
            f"  rpc={self.rpc}, \n"
            f"  chain_id={self.chain_id}, \n"
            f"  eip1559_tx={self.eip1559_tx}, \n"
            f"  coin_symbol={self.coin_symbol}, \n"
            f"  decimals={self.decimals}, \n"
            f"  explorer={self.explorer}) \n"
        )


class Networks:
    # Main-Nets
    Ethereum = Network(
        name='ethereum',
        rpc='https://rpc.ankr.com/eth/',
        chain_id=1,
        eip1559_tx=True,
        coin_symbol='ETH',
        explorer='https://etherscan.io/',
    )

    Arbitrum = Network(
        name='arbitrum',
        rpc='https://arbitrum.llamarpc.com',
        chain_id=42161,
        eip1559_tx=True,
        coin_symbol='ETH',
        explorer='https://arbiscan.io/',
    )

    Linea = Network(
        name='linea',
        rpc='https://linea.blockpi.network/v1/rpc/public',
        chain_id=59144,
        eip1559_tx=True,
        coin_symbol='ETH',
        explorer='https://lineascan.build/',
    )

    ArbitrumNova = Network(
        name='arbitrum_nova',
        rpc='https://nova.arbitrum.io/rpc/',
        chain_id=42170,
        eip1559_tx=True,
        coin_symbol='ETH',
        explorer='https://nova.arbiscan.io/',
    )

    Optimism = Network(
        name='optimism',
        rpc='https://rpc.ankr.com/optimism/',
        chain_id=10,
        eip1559_tx=True,
        coin_symbol='ETH',
        explorer='https://optimistic.etherscan.io/',
    )

    BSC = Network(
        name='bsc',
        rpc='https://rpc.ankr.com/bsc/',
        chain_id=56,
        eip1559_tx=False,
        coin_symbol='BNB',
        explorer='https://bscscan.com/',
    )

    Polygon = Network(
        name='polygon',
        rpc='https://rpc.ankr.com/polygon/',
        chain_id=137,
        eip1559_tx=True,
        coin_symbol='MATIC',
        explorer='https://polygonscan.com/',
    )

    ZkSync = Network(
        name='zksync',
        rpc="https://mainnet.era.zksync.io",
        chain_id=324,
        eip1559_tx=True,
        coin_symbol='ETH',
        explorer="https://explorer.zksync.io",
    )

    Avalanche = Network(
        name='avalanche',
        rpc='https://rpc.ankr.com/avalanche/',
        chain_id=43114,
        eip1559_tx=True,
        coin_symbol='AVAX',
        explorer='https://snowtrace.io/',
    )

    Moonbeam = Network(
        name='moonbeam',
        rpc='https://rpc.api.moonbeam.network/',
        chain_id=1284,
        eip1559_tx=True,
        coin_symbol='GLMR',
        explorer='https://moonscan.io/',
    )

    Fantom = Network(
        name='fantom',
        rpc='https://rpc.ftm.tools',
        chain_id=251,
        eip1559_tx=True,
        coin_symbol="FTM",
        explorer='',
    )

    Celo = Network(
        name='celo',
        rpc='https://forno.celo.org',
        chain_id=42220,
        eip1559_tx=True,
        coin_symbol="FTCELOM",
        explorer='',
    )

    Gnosis = Network(
        name='gnosis',
        rpc='https://rpc.gnosischain.com',
        chain_id=100,
        eip1559_tx=True,
        coin_symbol="XDAI",
        explorer='',
    )

    HECO = Network(
        name='HECO',
        rpc='https://http-mainnet.hecochain.com',
        chain_id=128,
        eip1559_tx=True,
        coin_symbol="HT",
        explorer='',
    )

    # Test-Nets
    Goerli = Network(
        name='goerli',
        rpc='https://rpc.ankr.com/eth_goerli/',
        chain_id=5,
        eip1559_tx=True,
        coin_symbol='ETH',
        explorer='https://goerli.etherscan.io/',
    )

    Sepolia = Network(
        name='sepolia',
        rpc="https://rpc.sepolia.org",
        chain_id=11155111,
        eip1559_tx=True,
        coin_symbol="ETH",
        explorer='',
    )

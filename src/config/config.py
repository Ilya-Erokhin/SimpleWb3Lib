import os
import sys
from pathlib import Path


if getattr(sys, 'frozen', False):
    ROOT_DIR = Path(sys.executable).parent.parent.absolute()
else:
    ROOT_DIR = Path(__file__).parent.parent.parent.absolute()

ABIS_DIR = os.path.join(ROOT_DIR, 'abis')

TOKEN_ABI = os.path.join(ABIS_DIR, 'token.json')
WOOFI_ABI = os.path.join(ABIS_DIR, 'woofi.json')

PRIVATE_KEYS_FILE = os.path.join(ROOT_DIR, 'data', 'private_keys.txt')
PROXIES_FILE = os.path.join(ROOT_DIR, 'data', 'proxies.txt')

import itertools


def load_proxies(proxies_file: str) -> itertools.cycle:
    """
    Loads proxies from a file and returns an iterator for cyclic use.

    :param proxies_file: Path to the file containing proxy configurations.
    :return: An iterator cycling through proxies.
    """
    try:
        with open(proxies_file, 'r') as f:
            proxies = [line.strip() for line in f if line.strip()]
        if proxies:
            return itertools.cycle(proxies)
        else:
            return None  # No proxies provided
    except FileNotFoundError:
        return None

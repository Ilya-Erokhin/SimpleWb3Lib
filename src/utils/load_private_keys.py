
def load_private_keys(file_path: str) -> list:
    """
    Загрузка приватных ключей из текстового файла.

    :param file_path: Путь к файлу с приватными ключами.
    :return: Список приватных ключей.
    """
    with open(file_path, 'r') as f:
        private_keys: list = [line.strip() for line in f if line.strip()]
    return private_keys

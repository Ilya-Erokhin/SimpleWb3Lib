import json


def read_json(path: str, encoding: str | None = None) -> list | dict:
    return json.load(open(path, encoding=encoding))

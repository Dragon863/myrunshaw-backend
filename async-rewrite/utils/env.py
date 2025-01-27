import os


def getFromEnv(key: str) -> str:
    """Get a value from the environment, or raise an error if it's not set"""
    value = os.getenv(key)
    if value is None:
        raise ValueError(f"Environment variable {key} is not set")
    return value

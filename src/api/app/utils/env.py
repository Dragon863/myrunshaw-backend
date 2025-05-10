import os
import dotenv

dotenv.load_dotenv()

from app.utils.logging import Logger

logger = Logger("env_vars")


def getFromEnv(key: str) -> str:
    """Get a value from the environment, or raise an error if it's not set"""
    value = os.getenv(key)
    if value is None:
        logger.error(f"Environment variable {key} is not set")
        raise ValueError(f"Environment variable {key} is not set")
    return value

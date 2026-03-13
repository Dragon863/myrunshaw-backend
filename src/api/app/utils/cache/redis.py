import typing
import redis.asyncio as redis
from fastapi import HTTPException

from app.utils.logging import Logger
from app.utils.env import getFromEnv

REDIS_HOST = getFromEnv("REDIS_HOST")
REDIS_PORT = int(getFromEnv("REDIS_PORT"))

redis_pool: typing.Optional[redis.Redis] = None
logger = Logger("redis_pool")


async def initialise_redis_pool():
    global redis_pool
    if redis_pool is None:
        logger.info("Initializing Redis pool...")
        try:
            redis_pool = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                decode_responses=True,  # string responses please!
            )
            await redis_pool.ping()  # check it's actually alive
            logger.info("Redis pool initialized.")
        except Exception:
            logger.exception("Failed to initialize Redis pool.")
            redis_pool = None
    else:
        logger.info("Redis pool already initialized.")


async def close_redis_pool():
    global redis_pool
    if redis_pool:
        logger.info("Closing Redis pool...")
        try:
            await redis_pool.aclose()
            logger.info("Redis pool closed.")
        except Exception:
            logger.exception("Failed to close Redis pool.")
            raise
        finally:
            redis_pool = None


async def get_redis_conn() -> redis.Redis:
    if not redis_pool:
        logger.error("Redis pool is not initialized.")
        raise HTTPException(status_code=503, detail="Cache service unavailable")
    return redis_pool

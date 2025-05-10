import typing
import asyncpg
from fastapi import HTTPException

from app.utils.logging import Logger
from app.utils.env import getFromEnv
from app.utils.db.init import init_db

DATABASE_URL = getFromEnv("DATABASE_URL")
db_pool: typing.Optional[asyncpg.Pool] = None
logger = Logger("db_pool")


async def connect_db_internal():
    return await asyncpg.create_pool(
        DATABASE_URL,
        user="postgres",
        password=getFromEnv("DATABASE_PWD"),
    )


async def initialise_db_pool():
    global db_pool
    if db_pool is None:
        logger.info("Initializing database pool...")
        db_pool = await connect_db_internal()
        await init_db(db_pool, logger=logger)
        logger.info("Database pool initialized.")
    else:
        logger.info("Database pool already initialized.")


async def close_db_pool():
    global db_pool
    if db_pool:
        logger.info("Closing database pool...")
        await db_pool.close()
        db_pool = None
        logger.info("Database pool closed.")


async def get_db_conn():
    if not db_pool:
        logger.error("Database pool is not initialized.")
        raise HTTPException(status_code=503, detail="Database service unavailable")
    async with db_pool.acquire() as connection:
        yield connection

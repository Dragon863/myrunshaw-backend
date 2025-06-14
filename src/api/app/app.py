import logging
import typing
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.http import HTTPBearer
from apitally.fastapi import ApitallyMiddleware

from app.utils.logging import EndpointFilter
from app.utils.cache.redis import close_redis_pool, initialise_redis_pool
from app.utils.db.pool import initialise_db_pool, close_db_pool
from app.utils.env import getFromEnv

from app.routers.auth.router import authRouter
from app.routers.buses.router import busesRouter
from app.routers.friends.router import friendsRouter
from app.routers.profilepics.router import profilePicsRouter
from app.routers.timetable.router import timetableRouter
from app.routers.payment.router import paymentRouter

DATABASE_URL = getFromEnv("DATABASE_URL")


async def app_startup_event():
    print(
        "\x1b[31m****WARNING: Please ensure cron job for sync engine is enabled and functioning correctly****\x1b[0m"
    )
    await initialise_db_pool()
    await initialise_redis_pool()


async def app_shutdown_event():
    await close_db_pool()
    await close_redis_pool()


app = FastAPI(
    title="My Runshaw API",
    description="The API used by the backend of the My Runshaw app to manage friendships, timetables, push notifications, buses and more. To authenticate with this API, you must provide an Appwrite JWT in the Authorization header.",
    version=getFromEnv("API_VERSION"),
    on_startup=[app_startup_event],
    on_shutdown=[app_shutdown_event],
    contact={
        "name": "Daniel Benge",
        "url": "https://danieldb.uk",
    },
    terms_of_service="https://privacy.danieldb.uk/terms",
    servers=[
        {
            "url": "https://runshaw-api.danieldb.uk",
            "description": "Production server",
        },
        {
            "url": "http://localhost:5006",
            "description": "Local development server",
        },
    ],
)

for router in [
    authRouter,
    busesRouter,
    friendsRouter,
    profilePicsRouter,
    timetableRouter,
    paymentRouter,
]:
    app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# analytics

app.add_middleware(
    ApitallyMiddleware,
    client_id=getFromEnv("APITALLY_CLIENT_ID"),
    env="prod",
)

security = HTTPBearer()


@app.get(
    "/ping",
    tags=["Healthcheck"],
)
async def ping():
    """
    Called by Uptime Kuma to check the health of the API
    """
    return JSONResponse({"message": "pong"})


@app.get("/", include_in_schema=False)
async def root():
    """
    Root endpoint
    """
    return JSONResponse(
        {
            "message": "Welcome to the My Runshaw API. Please visit the documentation at /docs for more information."
        }
    )


uvicorn_logger = logging.getLogger("uvicorn.access")
uvicorn_logger.addFilter(EndpointFilter(path="/ping"))

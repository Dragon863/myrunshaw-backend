import contextlib
import logging
from time import perf_counter

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.http import HTTPBearer

from app.utils.logging import EndpointFilter, configure_logging
from app.utils.telemetry import setup_telemetry
from app.utils.cache.redis import close_redis_pool, initialise_redis_pool
from app.utils.db.pool import initialise_db_pool, close_db_pool
from app.utils.env import getFromEnv

from app.routers.auth.router import authRouter
from app.routers.buses.router import busesRouter
from app.routers.friends.router import friendsRouter
from app.routers.profilepics.router import profilePicsRouter
from app.routers.timetable.router import timetableRouter
from app.routers.payment.router import paymentRouter
from app.routers.admin.router import adminRouter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

DATABASE_URL = getFromEnv("DATABASE_URL")

configure_logging()

_startup_logger = logging.getLogger("startup")
_request_logger = logging.getLogger("requests")


async def app_startup_event():
    _startup_logger.warning(
        "****WARNING: Please ensure cron job for sync engine is enabled and functioning correctly****"
    )
    await initialise_db_pool()
    await initialise_redis_pool()


async def app_shutdown_event():
    await close_db_pool()
    await close_redis_pool()


@contextlib.asynccontextmanager
async def lifespan(app):
    await app_startup_event()
    yield
    await app_shutdown_event()


app = FastAPI(
    title="My Runshaw API",
    description="The API used by the backend of the My Runshaw app to manage friendships, timetables, push notifications, buses and more. To authenticate with this API, you must provide an Appwrite JWT in the Authorization header.",
    version=getFromEnv("API_VERSION"),
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
    lifespan=lifespan,
)

for router in [
    authRouter,
    busesRouter,
    friendsRouter,
    profilePicsRouter,
    timetableRouter,
    paymentRouter,
    adminRouter,
]:
    app.include_router(router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

setup_telemetry(app)
FastAPIInstrumentor.instrument_app(app)

security = HTTPBearer()


@app.middleware("http")
async def log_requests(request, call_next):
    if request.url.path == "/ping":
        return await call_next(request)

    start = perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((perf_counter() - start) * 1000, 2)
        _request_logger.exception(
            "Unhandled request error: %s %s failed after %sms",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = round((perf_counter() - start) * 1000, 2)
    log_method = _request_logger.info
    if response.status_code >= 500:
        log_method = _request_logger.error
    elif response.status_code >= 400:
        log_method = _request_logger.warning

    log_method(
        "HTTP %s %s -> %s in %sms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


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

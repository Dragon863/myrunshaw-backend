import asyncpg
from fastapi import Depends, APIRouter, Request
from fastapi.responses import JSONResponse
from app.utils.models import ExtraBusRequestBody
from app.utils.auth import validateToken, jwtToken
from app.utils.db.pool import get_db_conn
from app.utils.appwrite import get_admin_client
from appwrite.client import Client
from appwrite.services.users import Users


busesRouter = APIRouter(
    tags=["Buses"],
)


@busesRouter.get(
    "/api/bus",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Buses"],
)
async def get_buses(
    req: Request,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Gets bus bay information from the database
    """
    buses = await conn.fetch("SELECT * FROM bus")
    return [dict(bus) for bus in buses]


@busesRouter.get(
    "/api/bus/for",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Buses"],
)
async def get_bus_for(
    req: Request,
    user_id: str,
    adminClient: Client = Depends(get_admin_client),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Gets the bus number for a user with the given ID as a query parameter
    """
    friendship = await conn.fetchrow(
        """SELECT * FROM friend_requests
        WHERE status = 'accepted'
        AND ((sender_id = $1 AND receiver_id = $2)
        OR (sender_id = $2 AND receiver_id = $1))
        """,
        req.state.user_id.lower(),
        user_id.lower(),
    )
    if not friendship:
        return JSONResponse({"error": "Unauthorised access"}, 403)

    buses = await conn.fetch(
        "SELECT bus FROM extra_bus_subscriptions WHERE user_id = $1", user_id
    )

    users = Users(adminClient)
    user = users.get(user_id)
    preferences: dict = user.get("prefs", {"bus_number": None})

    toReturn = []
    if "bus_number" in preferences:
        if preferences["bus_number"]:
            toReturn.append(preferences["bus_number"])
        toReturn.append(preferences["bus_number"])

    for bus in buses:
        toReturn.append(bus["bus"])

    if len(toReturn) == 0:
        return JSONResponse("Not set")
    return JSONResponse(", ".join(toReturn))


@busesRouter.post(
    "/api/extra_buses/add",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Buses"],
)
async def add_extra_buses(
    req: Request,
    buses: ExtraBusRequestBody,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Subscribe to a bus number for push notifications
    """
    if not buses.bus_number:
        return JSONResponse({"error": "bus_number is required"}, 400)

    bus_number = buses.bus_number

    try:
        await conn.execute(
            "INSERT INTO extra_bus_subscriptions (user_id, bus) VALUES ($1, $2) ON CONFLICT DO NOTHING",
            req.state.user_id,
            bus_number,
        )
        return JSONResponse({"message": "Bus added successfully"}, 201)
    except Exception as e:
        return JSONResponse({"error": "Bus already added"}, 409)


@busesRouter.post(
    "/api/extra_buses/remove",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Buses"],
)
async def remove_extra_buses(
    req: Request,
    buses: ExtraBusRequestBody,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Unsubscribe from a bus number for push notifications
    """
    if not buses.bus_number:
        return JSONResponse({"error": "bus_number is required"}, 400)

    bus_number = buses.bus_number

    try:
        await conn.execute(
            "DELETE FROM extra_bus_subscriptions WHERE user_id = $1 AND bus = $2",
            req.state.user_id,
            bus_number,
        )
        return JSONResponse({"message": "Bus removed successfully"}, 201)
    except Exception as e:
        return JSONResponse({"error": "Bus not found"}, 404)


@busesRouter.get(
    "/api/extra_buses/get",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Buses"],
)
async def get_extra_buses(
    req: Request,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Get the extra bus numbers the user is subscribed to for push notifications
    """
    buses = await conn.fetch(
        "SELECT bus FROM extra_bus_subscriptions WHERE user_id = $1", req.state.user_id
    )
    return [dict(bus) for bus in buses]

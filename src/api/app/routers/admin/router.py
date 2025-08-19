import asyncpg
from fastapi import APIRouter
from fastapi import Depends
from appwrite.client import Client
from appwrite.services.users import Users
from appwrite.exception import AppwriteException
from fastapi.responses import JSONResponse
import redis
import asyncio

from app.utils.cache.redis import get_redis_conn
from app.routers.admin.models.responses import AdminUserInfoResponse
from app.utils.appwrite import get_admin_client
from app.utils.env import getFromEnv
from app.utils.db.pool import get_db_conn
from app.utils.auth import isAdmin, jwtToken, validateToken


adminRouter = APIRouter(
    tags=["Admin"],
    prefix="/api/admin",
    dependencies=[Depends(jwtToken), Depends(validateToken), Depends(isAdmin)],
    include_in_schema=False,  # this router isn't useful to 99% of users
)


@adminRouter.get(
    "/user/{user_id}",
)
async def getUserInfo(
    user_id: str,
    conn: asyncpg.Connection = Depends(get_db_conn),
    adminClient: Client = Depends(get_admin_client),
    redisConn: redis.Redis = Depends(get_redis_conn),
):
    user_id = user_id.lower()
    # This route fetches user information for the technician tab
    buses = await conn.fetch(
        "SELECT bus FROM extra_bus_subscriptions WHERE user_id = $1", user_id
    )

    rows = await conn.fetch(
        """SELECT * FROM friend_requests 
                WHERE (sender_id = $1 OR receiver_id = $1)
                AND status = 'accepted'
                ORDER BY updated_at ASC
            """,
        user_id,
    )
    friendRequests = rows
    # extract the other user's ID, because either sender_id or receiver_id will be equal to user_id
    otherUserIDs = {
        row["receiver_id"] if row["sender_id"] == user_id else row["sender_id"]
        for row in friendRequests
    }
    friends = []
    users = Users(adminClient)
    for otherUserID in otherUserIDs:
        try:
            name = await redisConn.get(f"user_name:{otherUserID}")
            if name is not None:
                user: dict = await asyncio.to_thread(users.get, otherUserID)
                name = user["name"] if user else None
                if name:
                    await redisConn.set(f"user_name:{otherUserID}", name)
                if name:
                    await redisConn.set(f"user_name:{otherUserID}", name)

            friends.append(
                {
                    "id": otherUserID,
                    "name": name,
                    "email": otherUserID + "@student.runshaw.ac.uk",
                }
            )
        except AppwriteException:
            # user doesn't exist in appwrite for some reason
            pass
    timetableRow = await conn.fetchrow(
        "SELECT url FROM timetable_associations WHERE user_id = $1", user_id
    )
    timetableURL = timetableRow["url"] if timetableRow else None

    runshawPayURL = None

    if timetableURL is not None:
        externalID = (
            timetableURL.split("?id=")[-1]
            if timetableURL and "?" in timetableURL
            else None
        )

        runshawPayURL = (
            f'{getFromEnv("PAY_BALANCE_URL")}{externalID}' if externalID else None
        )

    name = await redisConn.get(f"user_name:{user_id}")
    if name is None:
        user: dict = await asyncio.to_thread(users.get, user_id)
        name = user["name"] if user else None
        if name:
            await redisConn.set(f"user_name:{user_id}", name)
        else:
            name = "Unknown User"

    return AdminUserInfoResponse(
        user_id=user_id,
        name=name,
        buses=(
            ", ".join(
                bus["bus"]
                for bus in buses
                if isinstance(bus, asyncpg.Record) and "bus" in bus
            )
            if buses
            else ""
        ),
        friends=friends,
        timetable_url=timetableURL,
        runshaw_pay_url=runshawPayURL,
        pfp_url=f"{getFromEnv('APPWRITE_ENDPOINT')}/storage/buckets/profiles/files/{user_id}/view?project={getFromEnv('APPWRITE_PROJECT_ID')}",
    )


@adminRouter.get("/is_admin")
async def isRequesterAdmin():
    # Check if the requester is an admin
    return JSONResponse({"is_admin": True})

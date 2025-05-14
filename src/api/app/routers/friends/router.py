import aiohttp
import asyncpg
from fastapi import Depends, APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
import redis
from app.utils.cache.redis import get_redis_conn
from app.utils.env import getFromEnv
from app.utils.models import (
    BatchGetBody,
    BlockedID,
    FriendRequestBody,
    FriendRequestHandleBody,
)
from app.utils.notifications import sendNotification
from app.utils.auth import validateToken, jwtToken
from app.utils.db.pool import get_db_conn
from app.utils.appwrite import get_admin_client
from appwrite.client import Client
from appwrite.services.users import Users


friendsRouter = APIRouter(
    tags=["Friends"],
)


@friendsRouter.get(
    "/api/friends",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def get_friends(
    req: Request,
    auth_user: dict = Depends(validateToken),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """Fetch friends for the authenticated user."""
    try:
        rows = await conn.fetch(
            """SELECT * FROM friend_requests 
                WHERE (sender_id = $1 OR receiver_id = $1)
                AND status = 'accepted'
                ORDER BY updated_at ASC
            """,
            req.user_id.lower(),
        )
        return [dict(row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to fetch friends")


@friendsRouter.get(
    "/api/name/get/{user_id}",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def get_name(
    req: Request,
    user_id: str,
    auth_user: dict = Depends(validateToken),
    conn: asyncpg.Connection = Depends(get_db_conn),
    adminClient: Client = Depends(get_admin_client),
):
    """Fetch the name of a user by their ID."""
    try:
        users = Users(adminClient)
        user: dict = users.get(user_id)
        return JSONResponse({"name": user["name"]})
    except Exception as e:
        return JSONResponse({"error": "User not found"}, status_code=404)


@friendsRouter.post(
    "/api/name/get/batch",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def get_names(
    req: Request,
    body: BatchGetBody,
    auth_user: dict = Depends(validateToken),
    redis_conn: redis.Redis = Depends(get_redis_conn),
):
    """Fetch the names of multiple users by their IDs. Called on app startup.
    Uses Redis for caching."""
    try:
        names = {}
        user_ids_to_fetch_from_appwrite = []
        cache_prefix = "user_name:"
        # technically I don't need a TTL at all, but this is just in case the cache container goes down with appwrite staying up
        cache_ttl_seconds = 60 * 60 * 24 * 7

        # step 1: check cache
        for user_id in body.user_ids:
            cached_name = await redis_conn.get(f"{cache_prefix}{user_id}")
            if cached_name:
                names[user_id] = cached_name
            else:
                user_ids_to_fetch_from_appwrite.append(user_id)

        # step 2: fetch from appwrite
        if user_ids_to_fetch_from_appwrite:
            async with aiohttp.ClientSession() as session:
                for user_id in user_ids_to_fetch_from_appwrite:
                    try:
                        api_res = await session.get(
                            f"{getFromEnv('APPWRITE_ENDPOINT')}/users/{user_id}",
                            headers={
                                "x-appwrite-project": getFromEnv("APPWRITE_PROJECT_ID"),
                                "x-appwrite-key": getFromEnv("APPWRITE_API_KEY"),
                                "user-agent": "ApppwritePythonSDK/7.0.0",
                                "x-sdk-name": "Python",
                                "x-sdk-platform": "server",
                                "x-sdk-language": "python",
                                "x-sdk-version": "7.0.0",
                                "content-type": "application/json",
                            },
                        )
                        user_data = await api_res.json()
                        if api_res.status == 200 and "name" in user_data:
                            user_name = user_data["name"]
                            names[user_id] = user_name
                            # cache it
                            await redis_conn.set(
                                f"{cache_prefix}{user_id}",
                                user_name,
                                ex=cache_ttl_seconds,
                            )
                        else:
                            names[user_id] = "Unknown User"
                            await redis_conn.set(
                                f"{cache_prefix}{user_id}", "Unknown User", ex=600
                            )  # prevents a bunch of requests
                    except Exception as e:
                        # Consider logging the error e
                        names[user_id] = "Unknown User"

        # all requested user_ids must have an entry in the response
        for user_id in body.user_ids:
            if user_id not in names:
                names[user_id] = "Unknown User"  # fallback just in case

        return JSONResponse(
            names,
            media_type="application/json",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    except Exception as e:
        # Consider logging the error e
        return JSONResponse({"error": "Failed to fetch names"}, status_code=500)


@friendsRouter.post(
    "/api/block",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def unfriend_user(
    req: Request,
    blocked_id_body: BlockedID,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """Unfriends a user by their ID. Route name preserved for backward compatibility"""

    try:
        await conn.execute(
            """DELETE FROM friend_requests 
            WHERE (sender_id = $1 AND receiver_id = $2) 
                OR (sender_id = $2 AND receiver_id = $1)""",
            req.user_id.lower(),
            blocked_id_body.blocked_id.lower(),
        )
        await conn.execute(
            "INSERT INTO blocked_users (blocker_id, blocked_id) VALUES ($1, $2)",
            req.user_id.lower(),
            blocked_id_body.blocked_id.lower(),
        )
        return JSONResponse(
            {"message": "User blocked and friendship removed (if applicable)"},
            201,
        )
    except Exception as e:
        return JSONResponse({"error": "You are not friends with this user"}, 409)


@friendsRouter.delete(
    "/api/block",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def unblock_user(
    req: Request,
    blocked_id: BlockedID,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """Block a user by their ID."""

    try:
        await conn.execute(
            "DELETE FROM blocked_users WHERE blocker_id = $1 AND blocked_id = $2",
            (req.user_id.lower(), blocked_id.lower()),
        )
        return JSONResponse({"message": "User unblocked successfully"}, 201)
    except Exception as e:
        return JSONResponse({"error": "User is not blocked"}, 409)


@friendsRouter.post(
    "/api/friend-requests",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def send_friend_request(
    req: Request,
    request_body: FriendRequestBody,
    conn: asyncpg.Connection = Depends(get_db_conn),
    adminClient: Client = Depends(get_admin_client),
):
    """
    Send a friend request to a user by their ID.
    """
    receiver = request_body.receiver_id.lower()
    sender = req.user_id.lower()

    if not receiver:
        return JSONResponse({"error": "receiver_id is required"}, 400)

    if receiver == sender:
        return JSONResponse({"error": "Cannot send a friend request to yourself"}, 400)

    try:
        users = Users(adminClient)
        users.get(receiver)
    except Exception as e:
        return JSONResponse({"error": "Invalid receiver_id"}, 404)

    try:
        # First check if a friend request exists in either direction
        existing_request = await conn.fetchrow(
            "SELECT * FROM friend_requests WHERE (sender_id = $1 AND receiver_id = $2) OR (sender_id = $2 AND receiver_id = $1)",
            sender,
            receiver,
        )
        if existing_request:
            return JSONResponse({"error": "Friend request already exists"}, 409)

        await conn.execute(
            """
                INSERT INTO friend_requests (sender_id, receiver_id) VALUES ($1, $2)
            """,
            sender,
            receiver,
        )
        sendNotification(
            message="You have a new friend request!",
            userIds=[receiver],
            title="Friend Request",
            ttl=60 * 60 * 24 * 2,
            small_icon="friend",  # Fun story: this used to default to a bus icon, which seemed vaguely threatening for android users!
        )
        return JSONResponse({"message": "Friend request sent"}, 201)
    except Exception as e:
        return JSONResponse(
            {"error": "An error occurred while sending the friend request"}, 500
        )


@friendsRouter.get(
    "/api/friend-requests",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def get_friend_requests(
    req: Request,
    status: str = "pending",
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """Fetch friend requests for the authenticated user."""
    try:
        rows = await conn.fetch(
            "SELECT * FROM friend_requests WHERE receiver_id = $1 AND status = $2",
            req.user_id,
            status,
        )
        return [dict(row) for row in rows]
    except Exception as e:
        return JSONResponse({"error": "Failed to fetch friend requests"}, 500)


@friendsRouter.put(
    "/api/friend-requests/{request_id}",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Friends"],
)
async def handle_friend_request(
    req: Request,
    request_id: int,
    request_body: FriendRequestHandleBody,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Accept or decline a friend request by its ID.
    """
    action = request_body.action
    if action not in ["accept", "decline"]:
        return JSONResponse({"error": "Invalid action"}, 400)

    request = await conn.fetchrow(
        "SELECT * FROM friend_requests WHERE id = $1", request_id
    )
    if not request:
        return JSONResponse({"error": "Friend request not found"}, 404)

    if request["receiver_id"] != req.user_id:
        return JSONResponse({"error": "Unauthorised access"}, 403)

    if request["status"] != "pending":
        return JSONResponse({"error": "Friend request has already been handled"}, 409)

    if action == "accept":
        await conn.execute(
            "UPDATE friend_requests SET status = 'accepted' WHERE id = $1",
            request_id,
        )
        sendNotification(
            message="Your friend request has been accepted!",
            userIds=[request["sender_id"]],
            title="Friend Request Accepted",
            ttl=60 * 60 * 24 * 2,
            small_icon="friend",
        )
        return JSONResponse({"message": "Friend request accepted"}, 200)
    else:
        try:
            await conn.execute(
                """DELETE FROM friend_requests 
                WHERE (sender_id = $1 AND receiver_id = $2) 
                    OR (sender_id = $2 AND receiver_id = $1)""",
                request["sender_id"],
                request["receiver_id"],
            )

            sendNotification(
                message="Your friend request has been declined.",
                userIds=[request["sender_id"]],
                title="Friend Request Declined",
                ttl=60 * 60 * 24 * 2,
                small_icon="friend",
            )
            return JSONResponse({"message": "Friend request declined"}, 200)
        except Exception as e:
            return JSONResponse({"error": "Failed to decline friend request"}, 500)

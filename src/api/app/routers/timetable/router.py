import re
import asyncpg
from fastapi import Depends, APIRouter, Request
from fastapi.responses import JSONResponse
import json
from app.sync import sync_timetable_for
from app.utils.auth import validateToken, jwtToken
from app.utils.db.pool import get_db_conn
from app.utils.models import (
    Timetable,
    BatchGetBody,
    TimetableAssociationBody,
)


timetableRouter = APIRouter(
    tags=["Timetable"],
)


@timetableRouter.post(
    "/api/timetable",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Timetable"],
)
async def add_timetable(
    req: Request,
    timetable: Timetable,
):
    """Add a timetable to the authenticated user's account."""
    try:
        # async with db_pool.acquire() as conn:
        #     await conn.execute(
        #         """INSERT INTO timetables (user_id, timetable)
        #         VALUES ($1, $2)
        #         ON CONFLICT (user_id)
        #         DO UPDATE SET timetable = $2, updated_at = CURRENT_TIMESTAMP""",
        #         req.user_id.lower(),
        #         json.dumps(timetable.dict()["timetable"]),
        #     )
        return JSONResponse({"message": "Timetable uploaded successfully"}, 201)
        # Logic removed in version 1.3.2 due to legacy sync deprecation
        # This is because the sync engine now handles this
    except Exception as e:
        return JSONResponse({"error": "Failed to upload timetable"}, 500)


@timetableRouter.get(
    "/api/timetable",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Timetable"],
)
async def get_timetable(
    req: Request,
    user_id: str | None = None,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Fetch the timetable for a user. If `user_id` is not provided, fetch the timetable
    for the requester. Only allow access if the requester is the user or their friend.
    """

    user_id = user_id or req.user_id  # If user_id_for is None, use the requester's ID

    if user_id != req.user_id:
        friendship = await conn.fetchrow(
            """SELECT * FROM friend_requests
            WHERE status = 'accepted'
            AND ((sender_id = $1 AND receiver_id = $2)
            OR (sender_id = $2 AND receiver_id = $1))
            """,
            req.user_id.lower(),
            user_id.lower(),
        )
        if not friendship:
            return JSONResponse({"error": "Unauthorised access"}, 403)

    timetable = await conn.fetchval(
        "SELECT timetable FROM timetables WHERE user_id = $1", user_id.lower()
    )

    if not timetable:
        return JSONResponse({"error": "Timetable not found"}, 404)

    return JSONResponse({"timetable": json.loads(timetable)})


@timetableRouter.post(
    "/api/timetable/batch_get",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Timetable"],
)
async def batch_get_timetable(
    req: Request,
    request_body: BatchGetBody,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """Fetch the timetables for multiple users. Called on app startup"""
    user_ids = request_body.user_ids
    if not req.user_id:
        return JSONResponse({"error": "No user IDs provided"}, 400)
    for user_id in user_ids:
        friendship = await conn.fetchrow(
            """SELECT * FROM friend_requests
            WHERE status = 'accepted'
            AND ((sender_id = $1 AND receiver_id = $2)
            OR (sender_id = $2 AND receiver_id = $1))
            """,
            req.user_id.lower(),
            user_id.lower(),
        )
        if not friendship and not user_id == req.user_id:
            return JSONResponse({"error": "Unauthorised access"}, 403)

    timetables = await conn.fetch(
        """
        SELECT user_id, timetable
        FROM timetables
        WHERE user_id = ANY($1::text[])
        """,
        user_ids,
    )

    # Ensure all requested users have a timetable entry
    for user_id in user_ids:
        if not any(row["user_id"] == user_id for row in timetables):
            timetables.append(
                {
                    "user_id": user_id,
                    "timetable": '{"data": []}',  # Ensuring valid JSON
                }
            )

    resp: JSONResponse = JSONResponse(
        {
            timetable["user_id"]: {
                "data": (
                    json.loads(timetable["timetable"] or '{"data": []}')["data"]
                    if type(timetable["timetable"]) == str
                    else timetable["timetable"]
                )
            }
            for timetable in timetables
        }
    )
    return resp


@timetableRouter.post(
    "/api/timetable/associate",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Timetable"],
)
async def get_meta(
    req: Request,
    body: TimetableAssociationBody,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """New in version 1.3.0 as migration to daily updating of timetables begins"""
    pattern = re.compile(r"https://webservices\.runshaw\.ac\.uk/timetable\.ashx\?id=.*")
    if not pattern.match(body.url):
        return JSONResponse(
            {"error": "Invalid URL. Must be a Runshaw timetable URL"}, 400
        )
    try:
        await conn.execute(
            """
            INSERT INTO timetable_associations (user_id, url)
            VALUES ($1, $2)
            ON CONFLICT (user_id) DO UPDATE SET url = $2
            """,
            req.user_id,
            body.url,
        )
        await sync_timetable_for(req.user_id, body.url)
        return JSONResponse({"message": "Timetable URL associated successfully"}, 201)
    except Exception as e:
        return JSONResponse({"error": "Failed to associate timetable URL"}, 500)

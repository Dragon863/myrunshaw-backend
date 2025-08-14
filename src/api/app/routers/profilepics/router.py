import asyncpg
from fastapi import Depends, APIRouter, Request
from fastapi.responses import JSONResponse
from app.utils.models import BatchGetBody
from app.utils.auth import validateToken, jwtToken
from app.utils.db.pool import get_db_conn
from app.utils.auth import validateToken, jwtToken


profilePicsRouter = APIRouter(
    tags=["Profile Pictures"],
)


@profilePicsRouter.post(
    "/api/cache/get/pfp-versions",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Profile Pictures"],
)
async def get_pfp_versions(
    req: Request, body: BatchGetBody, conn: asyncpg.Connection = Depends(get_db_conn)
):
    """This route will be called upon opening the app. It will return the current version of the profile pictures for the users provided in the JSON body under the key "user_ids"""
    if not body.user_ids:
        return JSONResponse({"error": "user_ids is required"}, 400)

    versions = await conn.fetch(
        "SELECT user_id, version FROM profile_pics WHERE user_id = ANY($1::text[])",
        body.user_ids,
    )

    for user_id in body.user_ids:
        if not any([row["user_id"] == user_id for row in versions]):
            versions.append(
                {
                    "user_id": user_id,
                    "version": 0,
                }
            )
            # Add an empty version for users that don't have one in the DB (often due to not updating since an old release or not at all)

    return JSONResponse(
        {version["user_id"]: version["version"] for version in versions}
    )


@profilePicsRouter.post(
    "/api/cache/update/pfp-version",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Profile Pictures"],
)
async def update_pfp_version(
    req: Request, conn: asyncpg.Connection = Depends(get_db_conn)
):
    """Update the version of a user's profile picture."""
    current_version = await conn.fetchval(
        "SELECT version FROM profile_pics WHERE user_id = $1", req.state.user_id
    )
    if not current_version:
        await conn.execute(
            "INSERT INTO profile_pics (user_id, version) VALUES ($1, $2)",
            req.state.user_id,
            1,
        )
    else:
        new_version = int(current_version) + 1

        await conn.execute(
            "UPDATE profile_pics SET version = $1 WHERE user_id = $2",
            new_version,
            req.state.user_id,
        )

    return JSONResponse(
        {"message": "Profile picture version updated successfully"}, 200
    )

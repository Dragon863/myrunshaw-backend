import aiohttp
import asyncpg
from fastapi import Depends, APIRouter, Request
from fastapi.responses import JSONResponse
from appwrite.client import Client
from appwrite.services.users import Users

from app.utils.appwrite import get_admin_client
from app.utils.auth import validateToken, jwtToken
from app.utils.db.pool import get_db_conn
from app.utils.env import getFromEnv
from app.utils.logging import Logger


authRouter = APIRouter(
    tags=["Auth"],
)
logger = Logger("auth_router")


@authRouter.get(
    "/api/exists/{user_id}",
    tags=["Auth"],
)
def user_exists(
    user_id: str,
    adminClient: Client = Depends(get_admin_client),
):
    try:
        users = Users(adminClient)
        users.get(user_id)
        return JSONResponse({"exists": True})
    except Exception as e:
        return JSONResponse({"exists": False}, 404)


@authRouter.post(
    "/api/account/close",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Compliance"],
)
async def close_account(
    req: Request,
    adminClient: Client = Depends(get_admin_client),
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """Close the authenticated user's account."""
    try:
        users = Users(adminClient)
        users.delete(req.user_id)

        await conn.execute(
            "DELETE FROM users WHERE user_id = $1",
            req.user_id,
        )

        app_id = getFromEnv("ONESIGNAL_APP_ID")
        alias_label = "external_id"
        alias_id = req.user_id

        url = (
            f"https://api.onesignal.com/apps/{app_id}/users/by/{alias_label}/{alias_id}"
        )
        headers = {
            "Authorization": f"Bearer {getFromEnv('ONESIGNAL_API_KEY')}",
        }

        response = await aiohttp.ClientSession().delete(url, headers=headers)
        if response.status != 200:
            logger.error(f"Failed to delete OneSignal user: {req.user_id}")

        return JSONResponse({"message": "Account deleted successfully"}, 200)

    except Exception as e:
        return JSONResponse({"error": "Failed to close account"}, 500)

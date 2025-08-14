import base64
import hashlib
import hmac
import aiohttp
import asyncpg
from typing import Annotated
from fastapi import Depends, APIRouter, Header, Request
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
        users.delete(req.state.user_id)

        await conn.execute(
            "DELETE FROM users WHERE user_id = $1",
            req.state.user_id,
        )

        app_id = getFromEnv("ONESIGNAL_APP_ID")
        alias_label = "external_id"
        alias_id = req.state.user_id

        url = (
            f"https://api.onesignal.com/apps/{app_id}/users/by/{alias_label}/{alias_id}"
        )
        headers = {
            "Authorization": f"Bearer {getFromEnv('ONESIGNAL_API_KEY')}",
        }

        response = await aiohttp.ClientSession().delete(url, headers=headers)
        if response.status != 200:
            logger.error(f"Failed to delete OneSignal user: {req.state.user_id}")

        return JSONResponse({"message": "Account deleted successfully"}, 200)

    except Exception as e:
        return JSONResponse({"error": "Failed to close account"}, 500)


@authRouter.post(
    "/api/webhook/appwrite/user-create",
    tags=["Auth"],
)
async def handle_appwrite_user_change(
    request: Request,
    x_appwrite_webhook_signature: Annotated[
        str | None,
        Header(
            description="Signature of the request, used to verify the authenticity of the webhook.",
        ),
    ] = None,
    x_appwrite_webhook_events: Annotated[
        str | None,
        Header(
            description="Events that triggered the webhook, used to determine action to take.",
        ),
    ] = None,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    This endpoint is called by Appwrite when a new user is created. It inserts it into the "users" table.
    """
    if not x_appwrite_webhook_signature:
        return JSONResponse({"error": "Bad signature request"}, 400)

    if getFromEnv("APPWRITE_USER_CREATION_WEBHOOK_SECRET"):
        # get payload as bytes
        raw_payload = await request.body()
        expected_signature = str.encode(
            getFromEnv("APPWRITE_USER_CREATION_WEBHOOK_SECRET")
        )

        if not raw_payload:
            return JSONResponse({"error": "Invalid JSON"}, 400)

        raw_data = request.url._url.encode() + raw_payload

        expected_signature = base64.b64encode(
            hmac.new(expected_signature, raw_data, hashlib.sha1).digest()
        )

        if not hmac.compare_digest(
            expected_signature, x_appwrite_webhook_signature.encode()
        ):
            return JSONResponse({"error": "Unauthorized"}, 401)
    else:
        logger.error(
            "No Appwrite webhook secret configured. Skipping signature verification."
        )
        return JSONResponse({"error": "Webhook secret not configured"}, 500)

    try:
        payload = await request.json()
        logger.debug(f"Received webhook payload: {payload}")

        if x_appwrite_webhook_events:
            if "create" in x_appwrite_webhook_events:
                user_id = payload["$id"]
                await conn.execute(
                    "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
                    user_id,
                )
                return JSONResponse({"message": "Webhook received, user created"}, 200)
            if "delete" in x_appwrite_webhook_events:
                user_id = payload["$id"]
                await conn.execute(
                    "DELETE FROM users WHERE user_id = $1",
                    user_id,
                )
                return JSONResponse({"message": "Webhook received, user deleted"}, 200)

    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        return JSONResponse({"error": "Invalid JSON"}, 400)

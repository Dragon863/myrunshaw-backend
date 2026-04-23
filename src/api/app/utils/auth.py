import sys
import os
import appwrite
from fastapi import HTTPException, Request
from appwrite.client import Client
from appwrite.exception import AppwriteException
from fastapi.security import HTTPBearer
from app.utils.env import getFromEnv
from app.utils.appwrite import run_appwrite_call
from app.utils.logging import Logger
from appwrite.services.account import Account
from appwrite.services.users import Users


logger = Logger("auth")


def _get_user_from_jwt(token: str):
    """Build and call Appwrite Account client in the same worker thread."""
    authClient = Client()
    authClient.set_endpoint(getFromEnv("APPWRITE_ENDPOINT"))
    authClient.set_project(getFromEnv("APPWRITE_PROJECT_ID"))
    authClient.set_jwt(token)
    account = Account(authClient)
    return account.get()


async def validateToken(req: Request):
    """Authenticate users with their JWT from Appwrite"""
    app_env = os.getenv("APP_ENV", "").lower()
    is_production = app_env in {"prod", "production"}

    if "pytest" in sys.modules and not is_production:
        # Will only every bypass token validation in tests
        auth_header = req.headers.get("Authorization")
        if auth_header and "Bearer" in auth_header:
            user_id = auth_header.split(" ")[1]
        else:
            user_id = auth_header
        req.state.user_id = user_id
        return {"$id": user_id, "name": "Test User"}

    token = ""
    try:
        authorization = req.headers.get("Authorization", None)
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized. Please provide an Authorization header.",
            )

        authorization = authorization.strip()
        parts = authorization.split(None, 1)

        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
        else:
            token = authorization

        if not token:
            raise HTTPException(status_code=401, detail="Unauthorized; missing token.")

        user = await run_appwrite_call(_get_user_from_jwt, token)

        if user is not None and user.id:
            req.state.user_id = user.id.lower()
        else:
            raise HTTPException(
                status_code=401, detail="Unauthorized; invalid user data."
            )
        return user
    except HTTPException:
        raise
    except AppwriteException as e:
        auth_header = req.headers.get("Authorization") or ""
        has_bearer_prefix = auth_header.lower().startswith("bearer ")
        logger.warning(
            f"Appwrite rejected token: code={e.code}, type={e.type}, has_bearer_prefix={has_bearer_prefix}, token_len={len(token) if 'token' in locals() else 0}"
        )
        raise HTTPException(status_code=401, detail="Unauthorized; invalid token.")
    except Exception:
        raise HTTPException(status_code=401, detail="Unauthorized; invalid token.")


async def isAdmin(req: Request):
    authedUser = await validateToken(req)

    adminClient = Client()
    adminClient.set_endpoint(getFromEnv("APPWRITE_ENDPOINT"))
    adminClient.set_project(getFromEnv("APPWRITE_PROJECT_ID"))
    adminClient.set_key(getFromEnv("APPWRITE_API_KEY"))

    users = Users(adminClient)
    result = await run_appwrite_call(users.list_memberships, user_id=authedUser.id)

    for membership in result.memberships:
        if membership.teamid == getFromEnv("APPWRITE_ADMIN_TEAM_ID"):
            return True

    raise HTTPException(status_code=403, detail="Forbidden; not an admin!")


jwtToken = HTTPBearer(
    description="JWT token from Appwrite. Use the format 'Bearer <token>'",
    scheme_name="Appwrite JWT",
    bearerFormat="JWT",
)

import sys
from fastapi import HTTPException, Request
from appwrite.client import Client
from fastapi.security import HTTPBearer
from app.utils.env import getFromEnv
from appwrite.services.account import Account
from appwrite.services.users import Users


async def validateToken(req: Request):
    """Authenticate users with their JWT from Appwrite"""
    if "pytest" in sys.modules:
        # Will only every bypass token validation in tests
        auth_header = req.headers.get("Authorization")
        if auth_header and "Bearer" in auth_header:
            user_id = auth_header.split(" ")[1]
        else:
            user_id = auth_header
        req.state.user_id = user_id
        return {"$id": user_id, "name": "Test User"}
    try:
        authorization = req.headers.get("Authorization", None)
        if not authorization:
            raise HTTPException(
                status_code=401,
                detail="Unauthorized. Please provide an Authorization header.",
            )
        if "Bearer" in authorization:
            token = authorization.split(" ")[1]
        else:
            token = authorization
        authClient = Client()
        authClient.set_endpoint(getFromEnv("APPWRITE_ENDPOINT"))
        authClient.set_project(getFromEnv("APPWRITE_PROJECT_ID"))
        authClient.set_jwt(token)
        account = Account(authClient)
        user = account.get()

        if isinstance(user, dict) and "$id" in user:
            req.state.user_id = user["$id"].lower()
        else:
            raise HTTPException(
                status_code=401, detail="Unauthorized; invalid user data."
            )
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail="Unauthorized; invalid token.")


async def isAdmin(req: Request):
    authedUser = await validateToken(req)

    adminClient = Client()
    adminClient.set_endpoint(getFromEnv("APPWRITE_ENDPOINT"))
    adminClient.set_project(getFromEnv("APPWRITE_PROJECT_ID"))
    adminClient.set_key(getFromEnv("APPWRITE_API_KEY"))

    users = Users(adminClient)
    result = users.list_memberships(user_id=authedUser["$id"])

    for membership in result["memberships"]:
        if membership["teamId"] == getFromEnv("APPWRITE_ADMIN_TEAM_ID"):
            return True

    raise HTTPException(status_code=403, detail="Forbidden; not an admin!")


jwtToken = HTTPBearer(
    description="JWT token from Appwrite. Use the format 'Bearer <token>'",
    scheme_name="Appwrite JWT",
    bearerFormat="JWT",
)

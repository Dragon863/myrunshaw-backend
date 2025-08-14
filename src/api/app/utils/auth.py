from fastapi import HTTPException, Request
from appwrite.client import Client
from fastapi.security import HTTPBearer
from app.utils.env import getFromEnv
from appwrite.services.account import Account


async def validateToken(req: Request):
    """Authenticate users with their JWT from Appwrite"""
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
            raise HTTPException(status_code=401, detail="Unauthorized; invalid user data.")
        return user
    except Exception as e:
        raise HTTPException(status_code=401, detail="Unauthorized; invalid token.")


jwtToken = HTTPBearer(
    description="JWT token from Appwrite. Use the format 'Bearer <token>'",
    scheme_name="Appwrite JWT",
    bearerFormat="JWT",
)

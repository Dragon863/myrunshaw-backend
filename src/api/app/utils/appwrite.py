import asyncio
from typing import Any, Callable

from appwrite.client import Client
from appwrite.services.users import Users
from app.utils.env import getFromEnv


async def run_appwrite_call(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run blocking Appwrite SDK calls in a thread to avoid blocking the event loop."""
    return await asyncio.to_thread(func, *args, **kwargs)


def get_admin_client() -> Client:
    """
    Get the Appwrite admin client
    Returns:
        Client: The Appwrite admin client
    """

    adminClient = Client()
    adminClient.set_endpoint(getFromEnv("APPWRITE_ENDPOINT"))
    adminClient.set_project(getFromEnv("APPWRITE_PROJECT_ID"))
    adminClient.set_key(getFromEnv("APPWRITE_API_KEY"))

    return adminClient

from appwrite.client import Client
from appwrite.services.users import Users
from app.utils.env import getFromEnv


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
    users = Users(adminClient)

    return adminClient

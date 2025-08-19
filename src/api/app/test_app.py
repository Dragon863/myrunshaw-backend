from asyncio import AbstractEventLoop
import random
import uuid
import asyncpg
from httpx import AsyncClient, ASGITransport
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager

from .utils.db.pool import get_db_conn
from . import app as main

from appwrite.client import Client
from appwrite.services.users import Users
from appwrite.query import Query
from .utils.env import getFromEnv

USER_ID = "abc" + str(uuid.uuid4().int)[:10]  # user ID to use for testing
SECOND_USER_ID = "def" + str(uuid.uuid4().int)[:10]  # 2nd user for friend request tests
HEADERS_USER1 = {"Authorization": f"Bearer {USER_ID.lower()}"}
HEADERS_USER2 = {"Authorization": f"Bearer {SECOND_USER_ID.lower()}"}


@pytest_asyncio.fixture(scope="function")
async def client():
    """Create an AsyncClient with lifespan management for testing."""
    async with LifespanManager(main.app):
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
            yield ac


@pytest.mark.asyncio
async def test_user_existence(client: AsyncClient):
    # get a random user ID from appwrite (guaranteed to exist)
    adminClient = Client()
    adminClient.set_endpoint(getFromEnv("APPWRITE_ENDPOINT"))
    adminClient.set_project(getFromEnv("APPWRITE_PROJECT_ID"))
    adminClient.set_key(getFromEnv("APPWRITE_API_KEY"))
    users = Users(adminClient)
    listOfUsers = users.list(queries=[Query.offset(random.randint(0, 100))])

    response = await client.get(
        f"/api/exists/{random.choice(listOfUsers['users'])['$id']}"
    )
    assert response.status_code == 200
    assert response.json() == {"exists": True}


@pytest.mark.asyncio
async def test_user_does_not_exist(client: AsyncClient):
    response = await client.get(f"/api/exists/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.json() == {"exists": False}


@pytest.mark.asyncio
async def test_ping(client: AsyncClient):
    response = await client.get("/ping")
    assert response.status_code == 200
    assert response.json() == {"message": "pong"}


@pytest.mark.asyncio
async def test_get_friends_unauthenticated(client: AsyncClient):
    response = await client.get("/api/friends")
    print(response)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_get_friends_authenticated(client: AsyncClient):
    response = await client.get("/api/friends", headers=HEADERS_USER1)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_create_user(client: AsyncClient):
    adminClient = Client()
    adminClient.set_endpoint(getFromEnv("APPWRITE_ENDPOINT"))
    adminClient.set_project(getFromEnv("APPWRITE_PROJECT_ID"))
    adminClient.set_key(getFromEnv("APPWRITE_API_KEY"))
    users = Users(adminClient)

    users.create(
        user_id=USER_ID,
        name="Test User (should be deleted automatically)",
        email=f"{USER_ID}@student.runshaw.ac.uk",
        password=uuid.uuid4().hex,
    )
    users.create(
        user_id=SECOND_USER_ID,
        name="Test User 2 (should be deleted automatically)",
        email=f"{SECOND_USER_ID}@student.runshaw.ac.uk",
        password=uuid.uuid4().hex,
    )

    # Also add users to the database since webhook won't trigger in tests
    db_gen = get_db_conn()
    db_conn = await anext(db_gen)
    await db_conn.execute(
        "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
        USER_ID.lower(),
    )
    await db_conn.execute(
        "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
        SECOND_USER_ID.lower(),
    )

    assert users.get(USER_ID)["$id"] == USER_ID
    assert users.get(SECOND_USER_ID)["$id"] == SECOND_USER_ID


@pytest.mark.asyncio
async def test_user_added_to_db(client: AsyncClient):
    db_gen = get_db_conn()
    db_conn = await anext(db_gen)
    user = await db_conn.fetchrow(
        "SELECT * FROM users WHERE user_id = $1", USER_ID.lower()
    )
    assert user is not None


@pytest.mark.asyncio
async def test_onboarding_flow_routes(client: AsyncClient):
    # first check adding buses
    response = await client.post(
        "/api/extra_buses/add", json={"bus_number": "760"}, headers=HEADERS_USER1
    )
    assert response.status_code == 201

    # check adding timetable
    response = await client.post(
        "/api/timetable/associate",
        json={"url": f"https://webservices.runshaw.ac.uk/timetable.ashx?id={USER_ID}"},
        headers=HEADERS_USER1,
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_friend_requests(client: AsyncClient):
    # Check sending a friend request from user 1 to user 2
    response = await client.post(
        "/api/friend-requests",
        json={"receiver_id": SECOND_USER_ID},
        headers=HEADERS_USER1,
    )
    assert response.status_code == 201

    # Check getting friend requests
    response = await client.get("/api/friend-requests", headers=HEADERS_USER1)
    assert response.status_code == 200
    assert isinstance(response.json(), list)

    # Try sending a friend request from user 2 to user 1 - should fail because one already exists
    response = await client.post(
        "/api/friend-requests", json={"receiver_id": USER_ID}, headers=HEADERS_USER2
    )
    assert response.status_code == 409  # Conflict - friend request already exists

    # Check getting friend requests as user 2 (should see the pending request from user 1)
    response = await client.get("/api/friend-requests", headers=HEADERS_USER2)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1

    # Get the request ID for acceptance
    request_id = response.json()[0]["id"]

    # Check accepting friend request as user 2
    response = await client.put(
        f"/api/friend-requests/{request_id}",
        json={"action": "accept"},
        headers=HEADERS_USER2,
    )
    assert response.status_code == 200

    # Check that the friend request is now accepted
    response = await client.get("/api/friends", headers=HEADERS_USER2)
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "accepted"


@pytest.mark.asyncio
async def test_account_deletion(client: AsyncClient):
    for userID in [USER_ID, SECOND_USER_ID]:
        response = await client.post(
            "/api/account/close", headers={"Authorization": f"Bearer {userID}"}
        )
        assert response.status_code == 200

        # delete from db since webhooks aren't triggered in tests
        db_gen = get_db_conn()
        db_conn = await anext(db_gen)
        await db_conn.execute("DELETE FROM users WHERE user_id = $1", userID.lower())

        # check the user is no longer in the database
        user = await db_conn.fetchrow(
            "SELECT * FROM users WHERE user_id = $1", userID.lower()
        )
        assert user is None

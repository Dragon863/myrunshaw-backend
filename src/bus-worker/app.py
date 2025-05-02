import asyncio
from datetime import datetime
import asyncpg
import os
import requests
from bs4 import BeautifulSoup
import re as regex
import dotenv
import onesignal
from onesignal.api import default_api
from onesignal.model.notification import Notification
from onesignal.model.filter import Filter

dotenv.load_dotenv()

BASE_URL = os.getenv("BASE_URL")
DEBUG = False
DATABASE = None

required_env_vars = [
    "ONESIGNAL_API_KEY",
    "ONESIGNAL_APP_ID",
    "ONESIGNAL_BUS_CHANNEL",
    "ONESIGNAL_GENERIC_CHANNEL",
    "DATABASE_URL",
    "DATABASE_PWD",
    "BASE_URL",
]

for var in required_env_vars:
    if not os.getenv(var):
        raise EnvironmentError(f"Missing required environment variable: {var}")

onesignal_configuration = onesignal.Configuration(
    app_key=os.environ.get("ONESIGNAL_API_KEY"),
    # user_key=os.environ.get("ONESIGNAL_USER_KEY"),
)
onesignal_api = default_api.DefaultApi(
    onesignal.ApiClient(configuration=onesignal_configuration)
)


def sendNotification(
    message,
    userIds: list = [],
    title: str = "Notification",
    ttl: int = 60 * 10,
    filters: list = [],
    channel: str = os.getenv("ONESIGNAL_GENERIC_CHANNEL"),
    priority: int = 10,
    small_icon="ic_stat_onesignal_default",
):
    """
    message: str = The message to send to the user
    userIds: list<str> = The user IDs to send the message to (these are the external user IDs from appwrite i.e. student IDs)
    ttl: int = The time to live for the notification in seconds, 10 minutes is reasonable for a bus notification
    headings: dict = The headings for the notification, this is optional and will default to the message if not provided
    """
    notification = Notification(
        app_id=os.environ.get("ONESIGNAL_APP_ID"),
        contents={"en": message},
        include_external_user_ids=userIds,
        ttl=ttl,
        headings={"en": title},
        filters=filters,
        android_channel_id=channel,
        android_accent_color="E63009",
        is_android=True,
        is_ios=True,
        priority=priority,
        small_icon=small_icon,
    )
    if DEBUG:
        print(notification)
    else:
        response = onesignal_api.create_notification(notification)
        # print(response)


async def prepareDB():
    global DATABASE
    DATABASE = await asyncpg.create_pool(
        os.getenv("DATABASE_URL"),
        user="postgres",
        password=os.getenv("DATABASE_PWD"),
    )
    print("--- DB is online ---")


async def parseSite():
    response = requests.get(
        BASE_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3",
        },
    )
    if response.status_code != 200:
        print(f"Failed to load page: Status code {response.status_code}")
        return

    soup = BeautifulSoup(response.content, "html.parser")

    async with DATABASE.acquire() as conn:
        old_data = {
            row["bus_id"]: row["bus_bay"]
            for row in await conn.fetch("SELECT bus_id, bus_bay FROM bus")
        }

        new_data = {}

        for row in soup.find_all("tr"):
            cells = row.find_all("td")
            if len(cells) > 0:
                bus_id = cells[0].text.strip()
                bus_bay = cells[2].text.strip()

                # Validate bus_id - it's usually 3 digits, followed by optional letters
                if not regex.match(r"^\d{3,4}[A-Z]*$", bus_id):
                    continue

                # Normalize empty or invalid bays to "0", meaning the bus is not in a bay
                if bus_bay in ["", " "] or not regex.match(r"^[A-Z]?\d{1,2}$", bus_bay):
                    bus_bay = "0"

                # Save new data so we can check for a change (i.e., bus arrives)
                new_data[bus_id] = bus_bay

                # This is basically just an upsert
                await conn.execute(
                    """
                    INSERT INTO bus (bus_id, bus_bay)
                    VALUES ($1, $2)
                    ON CONFLICT (bus_id) DO UPDATE
                    SET bus_bay = EXCLUDED.bus_bay
                    """,
                    bus_id,
                    bus_bay,
                )

        # Compare old and new data to identify changes
        for bus_id, new_bay in new_data.items():
            old_bay = old_data.get(bus_id, "0")  # Default to "0" for new entries

            # Check if bay has changed, also we should probably ignore transitions to "0"
            if old_bay != new_bay and new_bay != "0":
                print(f"Bus {bus_id} changed from bay {old_bay} to bay {new_bay}")
                if old_bay == "0":
                    message = f"The {bus_id} bus has arrived in bay {new_bay}"
                else:
                    message = (
                        f"The {bus_id} bus has moved from bay {old_bay} to {new_bay}"
                    )

                # Notify about bus updates
                sendNotification(
                    message,
                    title="Bus Update!",
                    filters=[
                        Filter(field="tag", key="bus", relation="=", value=bus_id),
                        Filter(
                            field="tag", key="bus_optout", relation="!=", value="true"
                        ),
                    ],
                    channel=os.getenv("ONESIGNAL_BUS_CHANNEL"),
                )

                # Now check the extra bus subscriptions
                rows = await conn.fetch(
                    "SELECT user_id FROM extra_bus_subscriptions WHERE bus = $1",
                    bus_id,
                )

                ids = [row["user_id"] for row in rows]

                if ids:
                    sendNotification(
                        message,
                        userIds=ids,
                        title="Bus Update!",
                        channel=os.getenv("ONESIGNAL_BUS_CHANNEL"),
                    )


async def runLoop():
    if DEBUG:
        print(
            "\x1b[31m****WARNING: DEBUG MODE ENABLED. DO NOT USE IN PRODUCTION!! ****\x1b[0m"
        )
    else:
        print("\x1b[32m**** Bus Worker is online in PRODUCTION env! ****\x1b[0m")
    await prepareDB()
    while True:
        try:
            current_time = datetime.now()
            if current_time.hour == 0 and current_time.minute == 0:
                async with DATABASE.acquire() as conn:
                    await conn.execute("UPDATE bus SET bus_bay = '0'")
            elif (current_time.hour in [15, 16]) or DEBUG:
                await parseSite()
        except Exception as e:
            print(f"Error in main loop: {e}")

        await asyncio.sleep(10)


asyncio.run(runLoop())

from datetime import datetime
import time
import sqlite3
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


DATABASE = "data/bus.db"
BASE_URL = "https://webservices.runshaw.ac.uk/bus/busdepartures.aspx"
DEBUG = True

conn = sqlite3.connect(DATABASE, check_same_thread=False)
cursor = conn.cursor()

conn.execute(
    """
CREATE TABLE IF NOT EXISTS bus (
    bus_id TEXT PRIMARY KEY,
    bus_bay TEXT NOT NULL DEFAULT '0'
)
"""
)

database = sqlite3.connect(DATABASE)

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
    filter: Filter = None,
    icon: str = "ic_stat_onesignal_default",
    channel: str = os.getenv("ONESIGNAL_GENERIC_CHANNEL"),
    priority: int = 10,
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
        filters=[filter] if filter else None,
        android_channel_id=channel,
        small_icon=icon,
        android_accent_color="E63009",
    )

    response = onesignal_api.create_notification(notification)
    print(response)


def parseSite():
    response = requests.get(BASE_URL)

    if response.status_code != 200:
        raise Exception(f"Failed to load page: Status code {response.status_code}")

    soup = BeautifulSoup(response.content, "html.parser")

    cursor.execute("SELECT bus_id, bus_bay FROM bus")
    old_data = {row[0]: row[1] for row in cursor.fetchall()}

    new_data = {}

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) > 0:
            bus_id = cells[0].text.strip()
            bus_bay = cells[2].text.strip()

            # Validate bus_id - it's usually 3 digits, followed by optional letters
            if not regex.match(r"^\d{3,4}[A-Z]*$", bus_id):
                continue

            # Normalize empty or invalid bays to "0", meaning the bus is not in a bay :)
            if bus_bay in ["", " "] or not regex.match(r"^[A-Z]?\d{1,2}$", bus_bay):
                bus_bay = "0"

            # Save new data so we can check for a change (i.e.. bus arrives)
            new_data[bus_id] = bus_bay

            # This is basically just an upsert
            cursor.execute(
                "INSERT OR REPLACE INTO bus (bus_id, bus_bay) VALUES (?, ?)",
                (bus_id, bus_bay),
            )

    conn.commit()

    # Compare old and new data to identify changes
    for bus_id, new_bay in new_data.items():
        old_bay = old_data.get(bus_id, "0")  # Default to "0" for new entries

        # Check if bay has changed, also we should probably ignore transitions to "0"
        if old_bay != new_bay and new_bay != "0":
            print(f"Bus {bus_id} changed from bay {old_bay} to bay {new_bay}")

            # Pinnnngg!
            sendNotification(
                f"The {bus_id} bus has arrived in bay {new_bay}",
                title="Bus Update!",
                filter=Filter(field="tag", key="bus", relation="=", value=bus_id),
                channel=os.getenv("ONESIGNAL_BUS_CHANNEL"),
                icon="ic_stat_onesignal_bus",
            )


def main():
    while True:
        # Parse the site every 10 seconds between 15:00 and 17:00, then reset all buses to bay 0 at midnight because that's when runshaw does it
        current_time = datetime.now()
        if current_time.hour == 0 and current_time.minute == 0:
            cursor.execute("UPDATE bus SET bus_bay = '0'")
            conn.commit()
        elif (current_time.hour in [15, 16]) or DEBUG:
            parseSite()
            time.sleep(10)

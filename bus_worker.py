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
DEBUG = False

conn = sqlite3.connect(DATABASE, check_same_thread=False)
cursor = conn.cursor()

conn.execute(
    """
CREATE TABLE IF NOT EXISTS bus (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bus_id TEXT NOT NULL,
    bus_bay TEXT NOT NULL
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
    userIds,
    title: str,
    ttl: int = 60 * 10,
    filter: Filter = None,
    icon: str = "ic_stat_onesignal_default",
    channel: str = os.getenv("ONESIGNAL_GENERIC_CHANNEL"),
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
        android_accent_color="#E63009",
    )

    onesignal_api.create_notification(notification)


def parseSite():
    response = requests.get(BASE_URL)

    if response.status_code != 200:
        raise Exception(f"Failed to load page: Status code {response.status_code}")

    soup = BeautifulSoup(response.content, "html.parser")

    """
    Example HTML:
    <tr>
        <td>762</td> <- this is the bus ID, it will be three numbers (sometimes followed by a letter)
        <td>B12</td> <- this is the bay number, it will eiter be blank or a letter followed by a one or two digit number
    </tr>

    or for a bus that is not in a bay:
    <tr>
        <td>150B</td>
        <td></td> <- this cell will be empty, or may have a space in it
    </tr>
    """

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) == 2:
            bus_id = cells[0].text
            bus_bay = cells[1].text

            if not regex.match(r"^\d{3,4}[A-Z]*$", bus_id):
                continue

            if bus_bay in ["", " "]:
                bus_bay = "0"

            if not regex.match(r"^[A-Z]?\d{1,2}$", bus_bay):
                continue

            cursor.execute(
                "INSERT INTO bus (bus_id, bus_bay) VALUES (?, ?)",
                (bus_id, bus_bay),
            )

    cursor.execute("SELECT bus_id, bus_bay FROM bus")
    old_data = {row[0]: row[1] for row in cursor.fetchall()}

    conn.commit()

    cursor.execute("SELECT bus_id, bus_bay FROM bus")
    new_data = {row[0]: row[1] for row in cursor.fetchall()}

    changed_buses = [
        (bus_id, old_data[bus_id], new_data[bus_id])
        for bus_id in new_data
        if bus_id in old_data and old_data[bus_id] != new_data[bus_id]
    ]

    if changed_buses:
        for bus_id, old_bay, new_bay in changed_buses:
            if new_bay != "0":
                print(f"Bus {bus_id} changed from bay {old_bay} to bay {new_bay}")
                sendNotification(
                    f"Your bus has arrived in bay {new_bay}",
                    [bus_id],
                    "Bus Update!",
                    filter=Filter(field="tag", key="bus", relation="=", value=bus_id),
                    channel=os.getenv("ONESIGNAL_BUS_CHANNEL"),
                    icon="ic_stat_onesignal_bus",
                )


def main():
    while True:
        # Parse the site every 10 seconds between 15:00 and 16:30, then reset all buses to bay 0 at midnight
        current_time = datetime.now()
        if current_time.hour == 0 and current_time.minute == 0:
            cursor.execute("UPDATE bus SET bus_bay = '0'")
            conn.commit()
        elif (current_time.hour == 15 and 0 <= current_time.minute <= 30) or DEBUG:
            parseSite()
        time.sleep(10)

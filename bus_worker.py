from datetime import datetime
import time
import sqlite3
import requests
from bs4 import BeautifulSoup
import re as regex


DATABASE = "data/bus.db"
BASE_URL = "https://webservices.runshaw.ac.uk/bus/busdepartures.aspx"
DEBUG = True

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

    conn.commit()


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

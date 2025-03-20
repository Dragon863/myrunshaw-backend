"""
Author: Daniel Benge
Date: 2025-14-03
Version: 1.0
Description: This script is used to fetch the timetable URLs from the database and parse the ICS files to JSON. I'll probably set it up as a daily cron job to keep the database up to date.
"""

import requests
import json
import uuid
from icalendar import Calendar
import psycopg2
import os
import dotenv

dotenv.load_dotenv()

conn = psycopg2.connect(
    f"user=postgres password={os.getenv('DATABASE_PWD')} host=localhost"
)


def parse_timetable(ics_url):
    response = requests.get(ics_url)
    response.raise_for_status()

    cal = Calendar.from_ical(response.text)

    json_data = {
        "version": "2.0",
        "prodid": "-//Runshaw College//EN",
        "method": "PUBLISH",
        "data": [],
    }

    for component in cal.walk():
        if component.name == "VEVENT":
            event = {
                "type": "VEVENT",
                "dtstart": {
                    "dt": component.get("dtstart").dt.strftime("%Y%m%dT%H%M%SZ")
                },
                "dtend": {"dt": component.get("dtend").dt.strftime("%Y%m%dT%H%M%SZ")},
                "dtstamp": {
                    "dt": component.get("dtstamp").dt.strftime("%Y%m%dT%H%M%SZ")
                },
                "uid": str(uuid.uuid4()),
                "created": (
                    {"dt": component.get("created").dt.strftime("%Y%m%dT%H%M%SZ")}
                    if component.get("created")
                    else {"dt": component.get("dtstamp").dt.strftime("%Y%m%dT%H%M%SZ")}
                ),
                "description": component.get("description"),
                "lastModified": (
                    {"dt": component.get("last-modified").dt.strftime("%Y%m%dT%H%M%SZ")}
                    if component.get("last-modified")
                    else {"dt": component.get("dtstamp").dt.strftime("%Y%m%dT%H%M%SZ")}
                ),
                "location": component.get("location"),
                "sequence": str(component.get("sequence", "0")),
                "status": component.get("status", "CONFIRMED"),
                "summary": component.get("summary"),
                "transp": component.get("transp", "OPAQUE"),
            }
            json_data["data"].append(event)

    return json.dumps(
        json_data,
        indent=0,
    )


query = "SELECT user_id, url FROM timetable_associations;"

with conn.cursor() as cursor:
    cursor.execute(query)
    for user_id, url in cursor.fetchall():
        print(f"User ID: {user_id}")
        jsonTimetable = (parse_timetable(url),)
        # Convert to a JSON to insert into the database

        cursor.execute(
            """INSERT INTO timetables (user_id, timetable)
       VALUES (%s, %s)
       ON CONFLICT (user_id)
       DO UPDATE SET timetable = %s, updated_at = CURRENT_TIMESTAMP""",
            (user_id, jsonTimetable, jsonTimetable),
        )

conn.commit()
conn.close()

"""
Author: Daniel Benge
Date: 2025-14-03
Version: 1.0
Description: This script is used to fetch the timetable URLs from the database and parse the ICS files to JSON. I'll probably set it up as a daily cron job to keep the database up to date.
"""

import aiohttp
import asyncpg
import json
import uuid
import os
import dotenv
import pytz
from icalendar import Calendar

dotenv.load_dotenv()

DB_CONFIG = {
    "user": "postgres",
    "password": os.getenv("DATABASE_PWD"),
    "host": "localhost",
    "port": 5432,
}


async def fetch_ics(ics_url):
    async with aiohttp.ClientSession() as session:
        async with session.get(ics_url) as response:
            response.raise_for_status()
            return await response.text()


async def parse_timetable(ics_url):
    ics_data = await fetch_ics(ics_url)
    cal = Calendar.from_ical(ics_data)

    json_data = {
        "version": "2.0",
        "prodid": "-//Runshaw College//EN",
        "method": "PUBLISH",
        "data": [],
    }

    london_tz = pytz.timezone("Europe/London")

    for component in cal.walk():
        if component.name == "VEVENT":
            dtstart = component.get("dtstart").dt
            dtend = component.get("dtend").dt
            dtstamp = component.get("dtstamp").dt

            dtstart = (
                dtstart.replace(tzinfo=pytz.UTC).astimezone(london_tz)
                if dtstart.tzinfo is None
                else dtstart.astimezone(london_tz)
            )
            dtend = (
                dtend.replace(tzinfo=pytz.UTC).astimezone(london_tz)
                if dtend.tzinfo is None
                else dtend.astimezone(london_tz)
            )
            dtstamp = (
                dtstamp.replace(tzinfo=pytz.UTC).astimezone(london_tz)
                if dtstamp.tzinfo is None
                else dtstamp.astimezone(london_tz)
            )

            event = {
                "type": "VEVENT",
                "dtstart": {"dt": dtstart.strftime("%Y%m%dT%H%M%S")},
                "dtend": {"dt": dtend.strftime("%Y%m%dT%H%M%S")},
                "dtstamp": {"dt": dtstamp.strftime("%Y%m%dT%H%M%S")},
                "uid": str(uuid.uuid4()),
                "created": (
                    {
                        "dt": component.get("created")
                        .dt.astimezone(london_tz)
                        .strftime("%Y%m%dT%H%M%S")
                    }
                    if component.get("created")
                    else {"dt": dtstamp.strftime("%Y%m%dT%H%M%S")}
                ),
                "description": component.get("description"),
                "lastModified": (
                    {
                        "dt": component.get("last-modified")
                        .dt.astimezone(london_tz)
                        .strftime("%Y%m%dT%H%M%S")
                    }
                    if component.get("last-modified")
                    else {"dt": dtstamp.strftime("%Y%m%dT%H%M%S")}
                ),
                "location": component.get("location"),
                "sequence": str(component.get("sequence", "0")),
                "status": component.get("status", "CONFIRMED"),
                "summary": component.get("summary"),
                "transp": component.get("transp", "OPAQUE"),
            }
            json_data["data"].append(event)

    return json.dumps(json_data, indent=0)


async def sync_timetable_for(user_id, url):
    json_timetable = await parse_timetable(url)

    conn = await asyncpg.connect(**DB_CONFIG)
    await conn.execute(
        """
        INSERT INTO timetables (user_id, timetable)
        VALUES ($1, $2)
        ON CONFLICT (user_id)
        DO UPDATE SET timetable = $2, updated_at = CURRENT_TIMESTAMP
        """,
        user_id,
        json_timetable,
    )
    await conn.close()

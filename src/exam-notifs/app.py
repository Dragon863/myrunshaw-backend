"""
This worker will check students' timetables for exams on the same day when
started by a cron job at 08:00 AM, queue them, and then send them at 08:45
(on the day of the exam). It picks a random message from a list of
encouraging messages to make the notifications a bit more fun and less robotic.
"""

import asyncio
from datetime import datetime
import asyncpg
import os
import json
import dotenv
import onesignal
from onesignal.api import default_api
from onesignal.model.notification import Notification
import random
import logging

dotenv.load_dotenv()

BASE_URL = os.getenv("BASE_URL")
DEBUG = False
DATABASE = None

# list of student IDs who have exams today; populated at 08:00 and cleared when sending
QUEUED_NOTIFICATIONS = []
QUEUED_NOTIFICATIONS_LOCK = None

# logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("exam-notifs")

MESSAGES = [
    "Good luck with your exam today - you've got this!",
    "Exam today - stay focused and do your best! :)",
    "Best of luck on your exam today!",
    "Wishing you all the best on your exam today :)",
    "All the best for your exam - stay focused and do your best!",
]

required_env_vars = [
    "ONESIGNAL_API_KEY",
    "ONESIGNAL_APP_ID",
    "ONESIGNAL_EXAM_CHANNEL",
    "ONESIGNAL_GENERIC_CHANNEL",
    "DATABASE_URL",
    "DATABASE_PWD",
]


def validate_env():
    missing = [v for v in required_env_vars if not os.getenv(v)]
    if missing:
        raise EnvironmentError(f"Missing required environment variables: {missing}")


onesignal_configuration = onesignal.Configuration(
    rest_api_key=os.environ.get("ONESIGNAL_API_KEY"),
)
onesignal_api = default_api.DefaultApi(
    onesignal.ApiClient(configuration=onesignal_configuration)
)


async def sendNotification(
    message,
    userIds: list = None,
    title: str = "Notification",
    ttl: int = 60 * 10,
    filters: list = None,
    channel: str = os.getenv("ONESIGNAL_GENERIC_CHANNEL"),
    priority: int = 10,
    small_icon="ic_app_logo",
):
    """Send notification via OneSignal.

    In DEBUG mode this prints the payload and does not call OneSignal.
    The actual network call is executed in a threadpool to avoid blocking the event loop.
    """
    global DEBUG
    if userIds is None:
        userIds = []
    if filters is None:
        filters = []

    # sanitize user IDs
    cleaned = [str(u).strip() for u in userIds if u and str(u).strip()]
    if not cleaned:
        logger.info("No valid user IDs to send notification to; skipping")
        return None

    notification = Notification(
        app_id=os.environ.get("ONESIGNAL_APP_ID"),
        contents={"en": message},
        include_external_user_ids=cleaned,
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
        logger.info(
            "DEBUG: would send notification: %s",
            {
                "message": message,
                "userIds": cleaned,
                "title": title,
                "ttl": ttl,
                "channel": channel,
            },
        )
        return None

    # perform blocking network call in executor
    try:
        loop = asyncio.get_running_loop()
        response = await loop.run_in_executor(
            None, onesignal_api.create_notification, notification
        )
        try:
            logger.info("OneSignal response: %s", response.to_dict())
        except Exception:
            logger.info("OneSignal response: %s", response)
        return response
    except Exception as e:
        logger.exception("Error sending OneSignal notification: %s", e)
        raise


async def prepareDB():
    global DATABASE
    validate_env()
    DATABASE = await asyncpg.create_pool(
        os.getenv("DATABASE_URL"),
        user="postgres",
        password=os.getenv("DATABASE_PWD"),
    )
    global QUEUED_NOTIFICATIONS_LOCK
    if QUEUED_NOTIFICATIONS_LOCK is None:
        QUEUED_NOTIFICATIONS_LOCK = asyncio.Lock()


async def queue_notifications():
    # This function will be called at 08:00 to populate the QUEUED_NOTIFICATIONS list with the student IDs of students who have exams today
    async with DATABASE.acquire() as connection:
        today = datetime.now().date()
        rows = await connection.fetch(
            """
            SELECT * FROM timetables
            """,
        )
        decoder = json.JSONDecoder()

        def parse_event_dt(dt_str: str) -> datetime:
            # Accept multiple datetime formats that may appear in timetables
            for fmt in (
                "%Y%m%dT%H%M%S",
                "%Y%m%dT%H%M",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M",
            ):
                try:
                    return datetime.strptime(dt_str, fmt)
                except Exception:
                    continue
            # fallback to fromisoformat if possible (may raise)
            try:
                return datetime.fromisoformat(dt_str)
            except Exception:
                raise ValueError(f"Unrecognized datetime format: {dt_str}")

        for user in rows:
            try:
                raw_tt = user.get("timetable")
                if isinstance(raw_tt, str):
                    timetable = decoder.decode(raw_tt)
                else:
                    timetable = raw_tt or {}
            except Exception:
                continue

            events = (timetable or {}).get("data", [])
            for event in events:
                # exams have a blank name for some reason
                if event.get("summary", None) == "":
                    try:
                        raw_dt = event["dtstart"]["dt"]
                        start_time = parse_event_dt(raw_dt)
                    except Exception:
                        continue

                    if start_time.date() == today:
                        user_id = user.get("user_id")
                        async with QUEUED_NOTIFICATIONS_LOCK:
                            if user_id and user_id not in QUEUED_NOTIFICATIONS:
                                QUEUED_NOTIFICATIONS.append(user_id)
                                logger.debug("Queued notification for user %s", user_id)
                        logger.debug("event: %s", event)
                        break


async def runMainLoop():
    await prepareDB()

    last_queue_date = None
    last_send_date = None

    while True:
        now = datetime.now()
        today = now.date()

        # At 08:00 populate the queue once per day
        if now.hour == 8 and last_queue_date != today:
            logger.info("[exam-notifs] running queue_notifications()")
            try:
                await queue_notifications()
            except Exception as e:
                logger.exception("Error during queue_notifications: %s", e)
            last_queue_date = today

        # At 08:45 send queued notifications once per day
        if now.hour == 8 and now.minute == 45 and last_send_date != today:
            logger.info("[exam-notifs] running send_queued_notifications()")
            try:
                await send_queued_notifications()
            except Exception as e:
                logger.exception("Error during send_queued_notifications: %s", e)
            last_send_date = today

        await asyncio.sleep(30)


async def send_queued_notifications():
    global QUEUED_NOTIFICATIONS
    async with QUEUED_NOTIFICATIONS_LOCK:
        if not QUEUED_NOTIFICATIONS:
            logger.info("[exam-notifs] no queued notifications to send")
            return
        recipients = list(QUEUED_NOTIFICATIONS)
        QUEUED_NOTIFICATIONS.clear()

    message = random.choice(MESSAGES)
    try:
        # send a single notification to all queued external user ids
        await sendNotification(
            message,
            userIds=recipients,
            title="Exam Today",
            ttl=60 * 60,
            channel=os.getenv("ONESIGNAL_EXAM_CHANNEL"),
            small_icon="app_logo",
        )
        logger.info("[exam-notifs] sent notifications to %d users", len(recipients))
    except Exception as e:
        logger.exception("[exam-notifs] error sending notifications: %s", e)


async def debug_test(sim_date: str, test_user: str):
    """Run a dry-run simulation: queue one fixed user and send notifications in debug mode."""
    global DEBUG, QUEUED_NOTIFICATIONS
    DEBUG = True
    print(f"[exam-notifs] DEBUG test: sim_date={sim_date}, test_user={test_user}")
    QUEUED_NOTIFICATIONS.clear()
    QUEUED_NOTIFICATIONS.append(test_user)
    await send_queued_notifications()


if __name__ == "__main__":
    sim_date = os.getenv("SIMULATE_DATE")
    sim_user = os.getenv("SIMULATE_USER")
    if sim_date and sim_user:
        # run a local debug simulation (dry-run): will print notification instead of sending
        asyncio.run(debug_test(sim_date, sim_user))
    else:
        asyncio.run(runMainLoop())

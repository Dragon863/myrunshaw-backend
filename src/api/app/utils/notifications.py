import onesignal
from onesignal.api import default_api
from onesignal.model.notification import Notification
from onesignal.model.filter import Filter
import dotenv
import os

dotenv.load_dotenv()

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
    # channel: str = os.getenv("ONESIGNAL_GENERIC_CHANNEL"),
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
        # android_channel_id=channel,
        android_accent_color="E63009",
        is_android=True,
        is_ios=True,
        priority=priority,
        small_icon=small_icon,
    )

    response = onesignal_api.create_notification(notification)

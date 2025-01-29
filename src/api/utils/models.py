import typing
from pydantic import BaseModel


class BlockedID(BaseModel):
    blocked_id: str


class Timetable(BaseModel):
    timetable: typing.Union[dict, str]


class BatchGetBody(BaseModel):
    user_ids: typing.List[str]


class ExtraBusRequestBody(BaseModel):
    bus_number: str


class FriendRequestBody(BaseModel):
    receiver_id: str


class FriendRequestHandleBody(BaseModel):
    action: str

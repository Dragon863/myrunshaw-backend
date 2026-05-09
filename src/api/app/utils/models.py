import typing
from pydantic import BaseModel, ConfigDict, Field


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


class TimetableAssociationBody(BaseModel):
    url: str  # Url of timetable


class WifiSpeedTestResultSubmission(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    download_speed_mbps: float = Field(alias="downloadSpeedMbps")
    upload_speed_mbps: float = Field(alias="uploadSpeedMbps")
    ping_times_ms: typing.List[float] = Field(alias="pingTimesMs", min_length=1)
    mean_latency_ms: float = Field(alias="meanLatencyMs")
    jitter_ms: float = Field(alias="jitterMs")
    platform: str
    bssid: str | None = None

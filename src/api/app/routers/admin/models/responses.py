from pydantic import BaseModel


class AdminUserInfoResponse(BaseModel):
    user_id: str
    name: str
    buses: str
    friends: list[dict]
    timetable_url: str | None
    runshaw_pay_url: str | None
    pfp_url: str

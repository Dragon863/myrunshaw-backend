import asyncio
import aiohttp
import asyncpg
from bs4 import BeautifulSoup
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
import re

from app.utils.env import getFromEnv
from app.utils.auth import validateToken
from app.utils.auth import jwtToken
from app.utils.db.pool import get_db_conn


paymentRouter = APIRouter(tags=["Payments"], prefix="/api/payments")


@paymentRouter.get(
    "/balance",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Payments"],
)
async def get_transactions(
    req: Request,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Fetch the user's timetable URL from the database and retrieve balance information from the RunshawPay page. This requires a JWT for authentication.
    """
    # fetch the user's timetable URL from the database
    try:
        async with conn.transaction():
            result = await conn.fetchrow(
                "SELECT url FROM timetable_associations WHERE user_id = $1",
                req.user_id.lower(),
            )
            user_id = (
                result["url"].split("?id=")[-1]
                if result and "?" in result["url"]
                else None
            )

            if not user_id:
                raise HTTPException(
                    status_code=404,
                    detail="No timetable URL found for the user.",
                )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Please sync your timetable first to use this feature!",
        )
    url = getFromEnv("PAY_BALANCE_URL") + user_id

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=3) as response:
                response.raise_for_status()
                html_content = await response.text()
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=408,
                detail="Request to RunshawPay timed out. Please try again later.",
            )

    soup = BeautifulSoup(html_content, "html.parser")

    balance_tag = soup.find("h1", class_="display-4")

    if balance_tag:
        balance = balance_tag.get_text().strip()
        return JSONResponse(
            {"balance": balance},
            status_code=200,
        )
    else:
        raise HTTPException(
            status_code=404,
            detail="Balance information not found in the HTML content.",
        )


@paymentRouter.get(
    "/transactions",
    dependencies=[Depends(validateToken), Depends(jwtToken)],
    tags=["Payments"],
)
async def get_transactions(
    req: Request,
    conn: asyncpg.Connection = Depends(get_db_conn),
):
    """
    Fetch the user's timetable URL from the database and retrieve balance information from the RunshawPay page. This requires a JWT for authentication.
    """
    # Fetch the user's timetable URL from the database
    try:
        async with conn.transaction():
            result = await conn.fetchrow(
                "SELECT url FROM timetable_associations WHERE user_id = $1",
                req.user_id.lower(),
            )
            user_id = (
                result["url"].split("?id=")[-1]
                if result and "?" in result["url"]
                else None
            )

            if not user_id:
                raise HTTPException(
                    status_code=404,
                    detail="Please sync your timetable first to use this feature!",
                )

        # The result has already been checked earlier, no need for redundant checks.

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="An error occurred - please ensure your timetable is synced, and if this persists please report it as a bug in settings",
        )
    url = getFromEnv("PAY_TRANSACTIONS_URL") + user_id

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=5) as response:
                response.raise_for_status()
                html_content = await response.text()
                soup = BeautifulSoup(html_content, "lxml")

                transaction_table = soup.find(
                    "table", id="ctl00_ctl00_bodyContent_bodyContent_gvTransactions"
                )

                if not transaction_table:
                    return []

                transactions_list = []

                # find all table rows `<tr>` within the table's body.
                # skip the first row `[1:]` because it contains the headers.
                rows = transaction_table.find_all("tr")[1:]

                for row in rows:
                    # find all data cells
                    cols = row.find_all("td")

                    # make sure the row has the expected number of columns - should be 4
                    if len(cols) == 4:
                        # date and details from the span
                        date_span = cols[0].find("span")
                        date = date_span.text.strip()
                        details = date_span.get("title", "").strip()

                        # action type
                        action = cols[1].text.strip()

                        # amount and balance - match using RegEx
                        amount_str = re.findall(r"[+-]?a?£[\d]+.[\d]+", str(cols[2]))
                        balance_str = re.findall(r"-?a?£[\d]+.[\d]+", str(cols[3]))

                        if not amount_str:
                            amount_str = "Err"
                        else:
                            amount_str = str(amount_str[0])
                        if not balance_str:
                            balance_str = "Err"
                        else:
                            balance_str = str(balance_str[0])

                        transaction = {
                            "date": date,
                            "details": details,
                            "action": action,
                            "amount": str(amount_str),
                            "balance": str(balance_str),
                        }
                        transactions_list.append(transaction)

                return JSONResponse(transactions_list)
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=408,
                detail="Request to RunshawPay timed out. Please try again later.",
            )

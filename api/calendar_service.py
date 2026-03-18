import json
import base64
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from api.config import (
    GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_CALENDAR_ID,
    TIMEZONE, BUSINESS_START_HOUR, BUSINESS_END_HOUR,
    BREAK_START_HOUR, BREAK_END_HOUR, SLOT_INCREMENT
)


def get_calendar_service():
    creds_json = json.loads(base64.b64decode(GOOGLE_SERVICE_ACCOUNT_JSON))
    creds = Credentials.from_service_account_info(
        creds_json, scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=creds)


def find_available_slots(target_date: str, duration: int) -> list[str]:
    """Find available time slots for a date (YYYY-MM-DD) and duration (minutes).
    Respects break hours and business hours."""
    service = get_calendar_service()
    tz = ZoneInfo(TIMEZONE)
    d = date.fromisoformat(target_date)

    time_min = datetime.combine(d, time(BUSINESS_START_HOUR, 0), tzinfo=tz).isoformat()
    time_max = datetime.combine(d, time(BUSINESS_END_HOUR, 0), tzinfo=tz).isoformat()

    events = service.events().list(
        calendarId=GOOGLE_CALENDAR_ID,
        timeMin=time_min, timeMax=time_max,
        singleEvents=True, orderBy="startTime", timeZone=TIMEZONE
    ).execute().get("items", [])

    # Build busy blocks from existing events
    busy = []
    for event in events:
        s = event.get("start", {}).get("dateTime")
        e = event.get("end", {}).get("dateTime")
        if s and e:
            start_dt = datetime.fromisoformat(s)
            end_dt = datetime.fromisoformat(e)
            busy.append((start_dt.hour * 60 + start_dt.minute,
                         end_dt.hour * 60 + end_dt.minute))

    # Add lunch break as a busy block
    busy.append((BREAK_START_HOUR * 60, BREAK_END_HOUR * 60))

    available = []
    for t in range(BUSINESS_START_HOUR * 60, BUSINESS_END_HOUR * 60 - duration + 1, SLOT_INCREMENT):
        slot_end = t + duration
        # Skip if slot overlaps with any busy block
        conflict = any(t < be and slot_end > bs for bs, be in busy)
        if not conflict:
            available.append(f"{t // 60:02d}:{t % 60:02d}")

    return available


def create_calendar_event(title: str, description: str, date_str: str,
                          start_time: str, duration: int) -> str:
    """Create a calendar event and return the event ID."""
    service = get_calendar_service()
    tz = ZoneInfo(TIMEZONE)

    start_dt = datetime.fromisoformat(f"{date_str}T{start_time}:00").replace(tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=duration)

    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
        "reminders": {
            "useDefault": False,
            "overrides": [{"method": "popup", "minutes": 30}]
        }
    }

    created = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    return created.get("id", "")

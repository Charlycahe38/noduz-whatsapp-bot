# SKILLS.md — Implementation Guide

## BUILD ORDER — FOLLOW THIS EXACT SEQUENCE

1. Project scaffolding (files, .env, vercel.json, requirements.txt, .gitignore)
2. Config module (load env vars)
3. Supabase client + SQL setup script (includes message_queue table)
4. WhatsApp client (send messages + parse incoming)
5. Webhook handlers (GET verify + POST receive)
6. Conversation service (load/save from Supabase)
7. Date parser (Spanish dates)
8. Google Calendar service (check availability + create events)
9. Appointments service (save confirmed bookings)
10. **Message Buffer — traffic-control layer (queue + per-customer lock)**
11. AI Agent (Gemini with tools — uses message buffer)
12. Wire everything together in index.py
13. Client Manager (multi-tenant UUID resolver)
14. Test script
15. Git + Vercel deployment config

---

## SKILL 1: Project Scaffolding

### requirements.txt
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
httpx==0.27.0
python-dotenv==1.0.1
supabase==2.9.0
google-genai==1.0.0
google-api-python-client==2.140.0
google-auth==2.35.0
python-dateutil==2.9.0
```

### .gitignore
```
__pycache__/
*.pyc
.env
SECRETS.md
google-credentials.json
*.json.bak
venv/
.vercel/
node_modules/
```

### vercel.json
```json
{
  "version": 2,
  "builds": [
    {
      "src": "api/index.py",
      "use": "@vercel/python"
    }
  ],
  "routes": [
    { "src": "/webhook", "dest": "api/index.py" },
    { "src": "/health", "dest": "api/index.py" },
    { "src": "/(.*)", "dest": "api/index.py" }
  ]
}
```

---

## SKILL 2: Configuration

### api/config.py
```python
import os
from dotenv import load_dotenv

load_dotenv()

# WhatsApp
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "noduz2026")
APP_SECRET = os.getenv("APP_SECRET", "")

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

# Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Google Calendar
GOOGLE_CALENDAR_ID = os.getenv("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")

# App
TIMEZONE = os.getenv("TIMEZONE", "America/Mexico_City")

# Services catalog
SERVICES = [
    {"name": "Corte de cabello", "duration": 30, "price": 150},
    {"name": "Corte + Barba", "duration": 45, "price": 250},
    {"name": "Solo Barba", "duration": 20, "price": 100},
    {"name": "Corte + Barba + Cejas", "duration": 60, "price": 300},
    {"name": "Tratamiento capilar", "duration": 45, "price": 350},
]

BUSINESS_START_HOUR = 9
BUSINESS_END_HOUR = 20
SLOT_INCREMENT = 30
```

---

## SKILL 3: Supabase Client + Schema

### api/supabase_client.py
```python
from supabase import create_client
from api.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

### SQL to run in Supabase SQL Editor (scripts/setup_supabase.sql)

```sql
-- Conversations: chat history + per-customer processing lock
CREATE TABLE conversations (
    id                 UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id          TEXT        NOT NULL,
    customer_phone     TEXT        NOT NULL,
    customer_name      TEXT        DEFAULT 'Cliente',
    messages           JSONB       DEFAULT '[]'::jsonb,
    last_message_at    TIMESTAMPTZ DEFAULT NOW(),
    created_at         TIMESTAMPTZ DEFAULT NOW(),
    -- Traffic-control columns (required for message_buffer.py)
    processing_lock    BOOLEAN     DEFAULT FALSE,
    lock_acquired_at   TIMESTAMPTZ
);

-- Message queue: every incoming message is saved here before AI processing
-- Enables burst buffering, per-customer locking, and zero message loss
CREATE TABLE message_queue (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id       TEXT        NOT NULL,
    customer_phone  TEXT        NOT NULL,
    customer_name   TEXT        DEFAULT 'Cliente',
    message_body    TEXT        NOT NULL,
    received_at     TIMESTAMPTZ DEFAULT NOW(),
    processed       BOOLEAN     DEFAULT FALSE
);

-- Appointments: confirmed bookings
CREATE TABLE appointments (
    id                 UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    client_id          TEXT        NOT NULL,
    customer_name      TEXT        NOT NULL,
    customer_phone     TEXT        NOT NULL,
    service            TEXT        NOT NULL,
    appointment_date   DATE        NOT NULL,
    start_time         TIME        NOT NULL,
    end_time           TIME        NOT NULL,
    duration_minutes   INTEGER     NOT NULL,
    price              DECIMAL(10,2) NOT NULL,
    currency           TEXT        DEFAULT 'MXN',
    google_event_id    TEXT,
    barber             TEXT,
    status             TEXT        DEFAULT 'confirmed',
    notes              TEXT,
    created_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Clients: one row per deployed bot instance (multi-tenant)
CREATE TABLE clients (
    id                          UUID  DEFAULT gen_random_uuid() PRIMARY KEY,
    business_name               TEXT,
    business_type               TEXT,
    business_location           TEXT,
    whatsapp_phone_id           TEXT  UNIQUE,
    whatsapp_token              TEXT,
    verify_token                TEXT,
    app_secret                  TEXT,
    gemini_api_key              TEXT,
    google_calendar_id          TEXT  DEFAULT 'primary',
    google_service_account_json TEXT,
    timezone                    TEXT  DEFAULT 'America/Mexico_City',
    working_days                TEXT,
    business_start_hour         INTEGER DEFAULT 9,
    business_end_hour           INTEGER DEFAULT 20,
    break_start_hour            INTEGER,
    break_end_hour              INTEGER,
    slot_increment              INTEGER DEFAULT 30,
    services                    JSONB   DEFAULT '[]'::jsonb,
    barbers                     JSONB   DEFAULT '[]'::jsonb,
    bot_language                TEXT,
    bot_greeting                TEXT,
    cancellation_policy         TEXT,
    post_confirmation_message   TEXT,
    deposit_required            BOOLEAN DEFAULT FALSE,
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX idx_conversations_client_phone ON conversations(client_id, customer_phone);
CREATE INDEX idx_message_queue_pending      ON message_queue(client_id, customer_phone, processed, received_at);
CREATE INDEX idx_appointments_date          ON appointments(client_id, appointment_date);
CREATE INDEX idx_appointments_phone         ON appointments(client_id, customer_phone);

-- RLS (open to service role — auth handled at app level)
ALTER TABLE conversations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE message_queue  ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments   ENABLE ROW LEVEL SECURITY;
ALTER TABLE clients        ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access" ON conversations  FOR ALL USING (true);
CREATE POLICY "Service role full access" ON message_queue  FOR ALL USING (true);
CREATE POLICY "Service role full access" ON appointments   FOR ALL USING (true);
CREATE POLICY "Service role full access" ON clients        FOR ALL USING (true);
```

> ⚠️ If adding traffic-control to an EXISTING deployment (not a fresh one), run
> `scripts/migrate_message_queue.sql` instead — it uses `ADD COLUMN IF NOT EXISTS`
> and `CREATE TABLE IF NOT EXISTS` so it won't break existing data.

---

## SKILL 4: WhatsApp Client

### api/whatsapp.py
```python
import httpx
from api.config import WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

async def send_message(to: str, message: str):
    url = f"https://graph.facebook.com/v21.0/{WHATSAPP_PHONE_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()
        if resp.status_code != 200:
            print(f"[whatsapp] Send failed to={to} status={resp.status_code}: {result}")
        return result

def parse_message(body: dict) -> dict | None:
    """Parse incoming WhatsApp webhook payload. Returns None if not a text message."""
    try:
        entry = body.get("entry", [{}])[0]
        changes = entry.get("changes", [{}])[0]
        value = changes.get("value", {})

        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        if msg.get("type") != "text":
            return None

        return {
            "phone_number_id": value.get("metadata", {}).get("phone_number_id", ""),
            "from": msg.get("from", ""),
            "name": value.get("contacts", [{}])[0].get("profile", {}).get("name", "Cliente"),
            "body": msg.get("text", {}).get("body", "").strip(),
            "message_id": msg.get("id", "")
        }
    except (IndexError, KeyError):
        return None
```

---

## SKILL 5: Webhook Handlers

### api/webhook.py

> ⚠️ CRITICAL: Do NOT use `BackgroundTasks` on Vercel. Vercel freezes the process
> after the response is sent — background tasks never execute. Process synchronously.

```python
import hashlib
import hmac
import traceback

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse
from api.config import VERIFY_TOKEN, APP_SECRET
from api.whatsapp import parse_message
from api.ai_agent import handle_incoming_message

router = APIRouter()

@router.get("/webhook")
async def verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        return PlainTextResponse(content=challenge)
    return PlainTextResponse(content="Forbidden", status_code=403)

@router.post("/webhook")
async def receive(request: Request):
    body_bytes = await request.body()

    if APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            APP_SECRET.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            print(f"[webhook] Invalid signature")
            return PlainTextResponse(content="Invalid signature", status_code=403)

    import json
    body = json.loads(body_bytes)
    message = parse_message(body)
    if not message:
        return {"status": "ok"}

    print(f"[webhook] Message from {message['from']}: {message['body'][:50]}")

    try:
        await handle_incoming_message(
            customer_phone=message["from"],
            customer_name=message["name"],
            message_body=message["body"]
        )
    except Exception as e:
        print(f"[webhook] Error: {e}\n{traceback.format_exc()}")

    return {"status": "ok"}
```

---

## SKILL 6: Conversation Service

> ⚠️ Always use `get_client_id()` from client_manager. NEVER upsert on `customer_phone` alone —
> the DB unique constraint is `(client_id, customer_phone)`.
>
> ⚠️ THREE BUGS to avoid in save_conversation (all caused the double-message error):
> 1. NEVER pass `"now()"` as a string for TIMESTAMPTZ — use `datetime.now(timezone.utc).isoformat()`
> 2. NEVER pass `json.dumps(list)` to a JSONB column — pass the Python list directly
> 3. NEVER use `upsert(on_conflict=...)` — use explicit select → update-or-insert instead,
>    because the unique constraint may not exist in production and upsert will silently fail

### api/conversation.py
```python
import json
from datetime import datetime, timezone
from api.supabase_client import supabase
from api.client_manager import get_client_id

async def get_conversation(phone: str) -> list:
    """Get conversation history for a customer scoped to this client."""
    client_id = get_client_id()
    result = (
        supabase.table("conversations")
        .select("*")
        .eq("client_id", client_id)
        .eq("customer_phone", phone)
        .execute()
    )
    if result.data:
        messages = result.data[0].get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        return messages
    return []

async def save_conversation(phone: str, name: str, messages: list):
    """Save conversation history — keep last 20 messages. Uses update-or-insert pattern."""
    client_id = get_client_id()
    trimmed = messages[-20:] if len(messages) > 20 else messages
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = (
        supabase.table("conversations")
        .select("id")
        .eq("client_id", client_id)
        .eq("customer_phone", phone)
        .execute()
    )

    if existing.data:
        supabase.table("conversations").update({
            "customer_name": name,
            "messages": trimmed,
            "last_message_at": now_iso,
        }).eq("client_id", client_id).eq("customer_phone", phone).execute()
    else:
        supabase.table("conversations").insert({
            "client_id": client_id,
            "customer_phone": phone,
            "customer_name": name,
            "messages": trimmed,
            "last_message_at": now_iso,
        }).execute()
```

---

## SKILL 7: Date Parser

### api/date_parser.py
```python
from datetime import date, timedelta
from zoneinfo import ZoneInfo
import re

def parse_spanish_date(text: str, timezone: str = "America/Mexico_City") -> str | None:
    """Parse Spanish date expressions and return YYYY-MM-DD string"""
    text_lower = text.lower().strip()
    today = date.today()

    # Direct keywords
    if text_lower in ["hoy", "today"]:
        return today.isoformat()
    if text_lower in ["mañana", "manana", "tomorrow"]:
        return (today + timedelta(days=1)).isoformat()
    if text_lower in ["pasado mañana", "pasado manana"]:
        return (today + timedelta(days=2)).isoformat()

    # Day names
    day_map = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6
    }
    for name, weekday in day_map.items():
        if name in text_lower:
            days_ahead = (weekday - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).isoformat()

    # DD/MM/YYYY format
    match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    return None
```

---

## SKILL 8: Google Calendar Service

### api/calendar_service.py
Use google-api-python-client with service account credentials.

```python
import json
import base64
from datetime import datetime, date, time, timedelta
from zoneinfo import ZoneInfo
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from api.config import (
    GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_CALENDAR_ID,
    TIMEZONE, BUSINESS_START_HOUR, BUSINESS_END_HOUR, SLOT_INCREMENT
)

def get_calendar_service():
    creds_json = json.loads(base64.b64decode(GOOGLE_SERVICE_ACCOUNT_JSON))
    creds = Credentials.from_service_account_info(
        creds_json, scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=creds)

def find_available_slots(target_date: str, duration: int) -> list[str]:
    """Find available time slots for a date (YYYY-MM-DD) and duration (minutes)"""
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

    # Build busy blocks
    busy = []
    for event in events:
        s = event.get("start", {}).get("dateTime")
        e = event.get("end", {}).get("dateTime")
        if s and e:
            start_dt = datetime.fromisoformat(s)
            end_dt = datetime.fromisoformat(e)
            busy.append((start_dt.hour * 60 + start_dt.minute, end_dt.hour * 60 + end_dt.minute))

    # Find free slots
    available = []
    for t in range(BUSINESS_START_HOUR * 60, BUSINESS_END_HOUR * 60 - duration + 1, SLOT_INCREMENT):
        slot_end = t + duration
        conflict = any(t < be and slot_end > bs for bs, be in busy)
        if not conflict:
            available.append(f"{t // 60:02d}:{t % 60:02d}")

    return available

def create_calendar_event(title: str, description: str, date_str: str,
                          start_time: str, duration: int) -> str:
    """Create a calendar event and return the event ID"""
    service = get_calendar_service()
    tz = ZoneInfo(TIMEZONE)

    start_dt = datetime.fromisoformat(f"{date_str}T{start_time}:00").replace(tzinfo=tz)
    end_dt = start_dt + timedelta(minutes=duration)

    event = {
        "summary": title,
        "description": description,
        "start": {"dateTime": start_dt.isoformat(), "timeZone": TIMEZONE},
        "end": {"dateTime": end_dt.isoformat(), "timeZone": TIMEZONE},
        "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": 30}]}
    }

    created = service.events().insert(calendarId=GOOGLE_CALENDAR_ID, body=event).execute()
    return created.get("id", "")
```

---

## SKILL 9: Appointments Service

### api/appointments.py
```python
from api.supabase_client import supabase
from api.client_manager import get_client_id

async def save_appointment(data: dict) -> dict:
    """Save appointment to Supabase."""
    client_id = get_client_id()
    record = {
        "client_id": client_id,
        "customer_name": data["customer_name"],
        "customer_phone": data["customer_phone"],
        "service": data["service_name"],
        "appointment_date": data["date"],
        "start_time": data["start_time"],
        "end_time": data.get("end_time", ""),
        "duration_minutes": data["duration_minutes"],
        "price": data["price"],
        "google_event_id": data.get("google_event_id", ""),
        "notes": data.get("barber", ""),
        "status": "confirmed",
    }
    result = supabase.table("appointments").insert(record).execute()
    return result.data[0] if result.data else {}
```

---

## SKILL 10: Message Buffer — Traffic-Control Layer

> ⚠️ REQUIRED for every deployment. Without this, burst messages from one customer
> trigger multiple concurrent AI calls → confused responses + rate limit errors.

### Why it exists
Vercel serverless has NO shared in-process memory between requests. Standard Python
locks (`asyncio.Lock`, `threading.Lock`) are invisible across concurrent invocations.
All coordination must live in Supabase.

### What it provides
- **Per-customer processing lock**: only one Vercel function processes a given customer at a time.
  Others save their message to the queue and return immediately.
- **Message queue**: every message is persisted before any AI work begins — zero message loss.
- **Debounce window**: the lock holder sleeps 2s so burst messages accumulate, turning
  "Hola / Quiero corte / Mañana / Con Daniel" (4 AI calls) into 1 combined request.
- **Stale-lock steal**: if a function crashes while holding the lock, it's stolen after 55s
  (just under Vercel's 60s timeout) so a crash never permanently blocks a customer.

### api/message_buffer.py
```python
from datetime import datetime, timezone, timedelta
from api.supabase_client import supabase
from api.client_manager import get_client_id

DEBOUNCE_SECONDS = 2
LOCK_STALE_AFTER = 55  # steal locks held longer than this

async def enqueue_message(customer_phone: str, customer_name: str, message_body: str) -> None:
    client_id = get_client_id()
    supabase.table("message_queue").insert({
        "client_id": client_id,
        "customer_phone": customer_phone,
        "customer_name": customer_name,
        "message_body": message_body,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
    }).execute()

async def try_acquire_lock(customer_phone: str) -> bool:
    """
    Atomic acquire: UPDATE WHERE processing_lock = FALSE.
    Postgres serializes concurrent UPDATEs on the same row — only one caller wins.
    Falls back to INSERT (new customer) or stale-lock steal.
    """
    client_id = get_client_id()
    now_iso = datetime.now(timezone.utc).isoformat()

    result = (
        supabase.table("conversations")
        .update({"processing_lock": True, "lock_acquired_at": now_iso})
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .eq("processing_lock", False)
        .execute()
    )
    if result.data:
        return True

    existing = (
        supabase.table("conversations")
        .select("processing_lock, lock_acquired_at")
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .execute()
    )

    if not existing.data:
        try:
            supabase.table("conversations").insert({
                "client_id": client_id,
                "customer_phone": customer_phone,
                "customer_name": "Cliente",
                "messages": [],
                "processing_lock": True,
                "lock_acquired_at": now_iso,
            }).execute()
            return True
        except Exception:
            return False  # another function inserted first

    row = existing.data[0]
    acquired_at_raw = row.get("lock_acquired_at")
    if acquired_at_raw:
        acquired_at = datetime.fromisoformat(acquired_at_raw.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - acquired_at).total_seconds()
        if age >= LOCK_STALE_AFTER:
            supabase.table("conversations").update({
                "processing_lock": True,
                "lock_acquired_at": now_iso,
            }).eq("client_id", client_id).eq("customer_phone", customer_phone).execute()
            return True

    return False  # lock is fresh, another function is processing

async def release_lock(customer_phone: str) -> None:
    client_id = get_client_id()
    supabase.table("conversations").update({
        "processing_lock": False,
        "lock_acquired_at": None,
    }).eq("client_id", client_id).eq("customer_phone", customer_phone).execute()

async def flush_pending_messages(customer_phone: str) -> list[dict]:
    """Fetch and mark processed all pending messages. Caller must hold the lock."""
    client_id = get_client_id()
    result = (
        supabase.table("message_queue")
        .select("*")
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .eq("processed", False)
        .order("received_at")
        .execute()
    )
    if not result.data:
        return []
    ids = [r["id"] for r in result.data]
    supabase.table("message_queue").update({"processed": True}).in_("id", ids).execute()
    return result.data

async def has_pending_messages(customer_phone: str) -> bool:
    client_id = get_client_id()
    result = (
        supabase.table("message_queue")
        .select("id")
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .eq("processed", False)
        .limit(1)
        .execute()
    )
    return bool(result.data)

def combine_messages(messages: list[dict]) -> str:
    """Join burst messages into one text block for a single AI turn."""
    bodies = [m["message_body"].strip() for m in messages if m.get("message_body", "").strip()]
    return "\n".join(bodies)
```

---

## SKILL 11: AI Agent (Gemini with Tool Use)

### api/ai_agent.py
This is the brain. It must:

1. Use the message buffer (SKILL 10) — never call AI directly from the webhook
2. Load conversation history from Supabase
3. Build system prompt with services, hours, current date
4. Call Gemini with conversation + tools
5. If Gemini returns function_call → execute the tool → feed result back → get final response
6. Send final text to customer via WhatsApp
7. Save updated conversation to Supabase

### handle_incoming_message — traffic-control entry point

> ⚠️ This is the ONLY public function called by webhook.py.
> It uses message_buffer.py (SKILL 10). Never call `_run_ai_for_message` directly.

```python
import asyncio
from api.message_buffer import (
    DEBOUNCE_SECONDS, combine_messages, enqueue_message,
    flush_pending_messages, has_pending_messages, release_lock, try_acquire_lock,
)

async def handle_incoming_message(customer_phone: str, customer_name: str, message_body: str):
    # 1. Persist first — never lose a message
    await enqueue_message(customer_phone, customer_name, message_body)

    # 2. Try to become the processor for this customer
    lock_acquired = await try_acquire_lock(customer_phone)
    if not lock_acquired:
        return  # another function holds the lock and will pick up this message

    try:
        while True:
            # 3. Debounce — let burst messages pile into the queue
            await asyncio.sleep(DEBOUNCE_SECONDS)

            # 4. Grab all pending messages and combine into one AI request
            messages = await flush_pending_messages(customer_phone)
            if not messages:
                break

            combined = combine_messages(messages)
            actual_name = messages[-1].get("customer_name") or customer_name

            try:
                await _run_ai_for_message(customer_phone, actual_name, combined)
            except Exception as e:
                print(f"[ai_agent] AI error for {customer_phone}: {e}")
                try:
                    await send_message(customer_phone,
                        "Dame un momento, estoy teniendo dificultades técnicas. Intenta de nuevo en unos segundos.")
                except Exception:
                    pass

            # 5. Check for messages that arrived while AI was thinking
            if not await has_pending_messages(customer_phone):
                break

    finally:
        # 6. Always release — even on crash — so the customer is never blocked
        await release_lock(customer_phone)
```

### _run_ai_for_message — core AI pipeline (called only by handle_incoming_message)

```python
async def _run_ai_for_message(customer_phone: str, customer_name: str, message_text: str):
    history = await get_conversation(customer_phone)
    history.append({"role": "user", "parts": [{"text": message_text}]})
    system_prompt = build_system_prompt()

    contents = [
        types.Content(role=m["role"], parts=[types.Part(text=m["parts"][0]["text"])])
        for m in history
    ]

    response = await _gemini_call(contents, system_prompt)

    # Tool-call loop
    for _ in range(5):
        parts = response.candidates[0].content.parts
        function_calls = [p for p in parts if p.function_call]
        if not function_calls:
            break
        tool_results = []
        for part in function_calls:
            result = await execute_tool(part.function_call.name, dict(part.function_call.args))
            tool_results.append(types.Part(
                function_response=types.FunctionResponse(
                    name=part.function_call.name, response={"result": result}
                )
            ))
        contents.append(types.Content(role="model", parts=parts))
        contents.append(types.Content(role="user", parts=tool_results))
        response = await _gemini_call(contents, system_prompt)

    final_text = "".join(
        p.text for p in response.candidates[0].content.parts if p.text
    ) if response.candidates and response.candidates[0].content else ""

    if not final_text:
        final_text = "Disculpa, hubo un problema. Por favor intenta de nuevo."

    await send_message(customer_phone, final_text)

    history.append({"role": "model", "parts": [{"text": final_text}]})
    try:
        await save_conversation(customer_phone, customer_name, history)
    except Exception as e:
        print(f"[ai_agent] save_conversation FAILED: {e}")
```

### Tool execution:
```python
async def execute_tool(tool_name: str, args: dict) -> str:
    if tool_name == "check_calendar_availability":
        slots = find_available_slots(args["date"], args["duration_minutes"])
        if not slots:
            return f"No hay horarios disponibles para {args['date']}."
        return f"Horarios disponibles para {args['date']}: {', '.join(slots)}"

    elif tool_name == "create_appointment":
        title = f"✂️ {args['service_name']} - {args['customer_name']}"
        description = (
            f"Cliente: {args['customer_name']}\n"
            f"Teléfono: {args['customer_phone']}\n"
            f"Servicio: {args['service_name']}\n"
            f"Precio: ${args['price']} MXN"
        )
        event_id = create_calendar_event(
            title, description, args["date"],
            args["start_time"], args["duration_minutes"]
        )
        end_minutes = int(args["start_time"].split(":")[0]) * 60 + \
                      int(args["start_time"].split(":")[1]) + args["duration_minutes"]
        end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"
        await save_appointment({**args, "end_time": end_time, "google_event_id": event_id})
        return f"Cita creada exitosamente. Evento ID: {event_id}"

    return "Herramienta no reconocida."
```

---

## SKILL 12: Main Entry Point

### api/index.py
```python
from fastapi import FastAPI
from api.webhook import router

app = FastAPI(title="Noduz WhatsApp Bot")
app.include_router(router)

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/")
async def root():
    return {"message": "Noduz WhatsApp Booking Bot is running"}
```

---

## SKILL 13: GitHub + Vercel Deployment

### Steps Claude Code should execute:
```bash
# 1. Initialize git
git init
git add .
git commit -m "Initial commit: Noduz WhatsApp Booking Bot"

# 2. Create GitHub repo (use gh CLI if available)
gh repo create noduz-whatsapp-bot --public --source=. --remote=origin --push

# 3. Install Vercel CLI
npm i -g vercel

# 4. Deploy to Vercel
vercel --prod
```

### After deployment:
- Copy the Vercel URL (e.g., `https://noduz-whatsapp-bot.vercel.app`)
- Go to Meta → WhatsApp → Configuration → Webhook
- URL: `https://noduz-whatsapp-bot.vercel.app/webhook`
- Verify Token: `noduz2026`
- Subscribe to "messages"

---

## TESTING

### scripts/test_conversation.py
Simulate a full booking conversation locally without WhatsApp:
```python
# Test the AI agent with mock messages
messages = [
    "Hola, buenas tardes",
    "Quiero un corte de cabello",
    "Para mañana",
    "A las 10 está bien",
    "Sí, confírmame"
]
# Process each message through the agent and print responses
```

### Verify each step:
1. Run locally: `uvicorn api.index:app --reload --port 5000`
2. Test health: `curl http://localhost:5000/health`
3. Test verify: `curl "http://localhost:5000/webhook?hub.mode=subscribe&hub.verify_token=noduz2026&hub.challenge=test123"`
4. Should return: `test123`

---

## SKILL 14: Client Manager (Multi-tenant UUID resolver)

Every deployment is linked to one row in the `clients` table via a UUID. This module
resolves that UUID automatically so you never need to hardcode it.

### api/client_manager.py
```python
"""
Priority order:
  1. CLIENT_ID env var (set in Vercel for production — fastest)
  2. DB lookup by WHATSAPP_PHONE_ID (auto-discovery on cold start)
  3. Auto-insert client row from config.py values (first-run setup)
Result is cached module-level — one DB call per cold start max.
"""
import os

_client_id_cache: str | None = None

def get_client_id() -> str:
    global _client_id_cache
    if _client_id_cache:
        return _client_id_cache

    env_id = os.getenv("CLIENT_ID", "").strip()
    if env_id:
        _client_id_cache = env_id
        return _client_id_cache

    from api.supabase_client import supabase
    from api.config import WHATSAPP_PHONE_ID
    result = supabase.table("clients").select("id").eq("whatsapp_phone_id", WHATSAPP_PHONE_ID).execute()
    if result.data:
        _client_id_cache = result.data[0]["id"]
        print(f"[client_manager] CLIENT_ID resolved from DB: {_client_id_cache}")
        return _client_id_cache

    # First run — create client row from config values
    from api.config import (WHATSAPP_TOKEN, VERIFY_TOKEN, APP_SECRET, BUSINESS_NAME,
        BUSINESS_TYPE, BUSINESS_LOCATION, GEMINI_API_KEY, GOOGLE_CALENDAR_ID,
        GOOGLE_SERVICE_ACCOUNT_JSON, TIMEZONE, WORKING_DAYS, BUSINESS_START_HOUR,
        BUSINESS_END_HOUR, BREAK_START_HOUR, BREAK_END_HOUR, SLOT_INCREMENT,
        SERVICES, BARBERS, BOT_LANGUAGE, BOT_GREETING_EXAMPLE,
        CANCELLATION_POLICY, POST_CONFIRMATION_MESSAGE, DEPOSIT_REQUIRED)
    record = {
        "business_name": BUSINESS_NAME, "business_type": BUSINESS_TYPE,
        "business_location": BUSINESS_LOCATION, "whatsapp_phone_id": WHATSAPP_PHONE_ID,
        "whatsapp_token": WHATSAPP_TOKEN, "verify_token": VERIFY_TOKEN,
        "app_secret": APP_SECRET, "gemini_api_key": GEMINI_API_KEY,
        "google_calendar_id": GOOGLE_CALENDAR_ID,
        "google_service_account_json": GOOGLE_SERVICE_ACCOUNT_JSON,
        "timezone": TIMEZONE, "working_days": WORKING_DAYS,
        "business_start_hour": BUSINESS_START_HOUR, "business_end_hour": BUSINESS_END_HOUR,
        "break_start_hour": BREAK_START_HOUR, "break_end_hour": BREAK_END_HOUR,
        "slot_increment": SLOT_INCREMENT, "services": SERVICES, "barbers": BARBERS,
        "bot_language": BOT_LANGUAGE, "bot_greeting": BOT_GREETING_EXAMPLE,
        "cancellation_policy": CANCELLATION_POLICY,
        "post_confirmation_message": POST_CONFIRMATION_MESSAGE,
        "deposit_required": DEPOSIT_REQUIRED,
    }
    create_result = supabase.table("clients").insert(record).execute()
    if not create_result.data:
        raise RuntimeError("[client_manager] Failed to create client row in Supabase")
    _client_id_cache = create_result.data[0]["id"]
    print(f"[client_manager] Created new client row: {_client_id_cache} — set CLIENT_ID={_client_id_cache} in Vercel env vars.")
    return _client_id_cache
```

### After first deploy — backfill existing data:
```sql
-- Run in Supabase SQL Editor after getting the UUID from Vercel logs
UPDATE conversations SET client_id = '<uuid>' WHERE client_id IS NULL;
UPDATE appointments  SET client_id = '<uuid>' WHERE client_id IS NULL;
```

---

## ERROR HANDLING PATTERNS

- Wrap ALL webhook processing in try/except
- Log errors with full traceback using print() (Vercel captures stdout)
- Send friendly error message to customer: "⚠️ Hubo un error. Por favor intenta de nuevo."
- Never let Gemini API errors crash the webhook
- If Google Calendar fails, tell customer "No pude verificar disponibilidad, intenta en unos minutos."
- **CRITICAL: Wrap `save_conversation` in its own try/except, separate from the main handler.**
  If the DB save fails AFTER `send_message` succeeded, the outer `except` would send the
  error message to the customer even though the AI response was delivered correctly.
  Pattern:
  ```python
  await send_message(customer_phone, final_text)
  history.append({"role": "model", "parts": [{"text": final_text}]})
  try:
      await save_conversation(customer_phone, customer_name, history)
  except Exception as save_err:
      print(f"[ai_agent] save_conversation FAILED: {save_err}\n{traceback.format_exc()}")
  # DO NOT re-raise — message was already delivered successfully
  ```

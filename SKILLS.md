# SKILLS.md — Implementation Guide

## BUILD ORDER — FOLLOW THIS EXACT SEQUENCE

1. Project scaffolding (files, .env, vercel.json, requirements.txt, .gitignore)
2. Config module (load env vars)
3. Supabase client + SQL setup script
4. WhatsApp client (send messages + parse incoming)
5. Webhook handlers (GET verify + POST receive)
6. Conversation service (load/save from Supabase)
7. Date parser (Spanish dates)
8. Google Calendar service (check availability + create events)
9. AI Agent (Gemini with tools)
10. Wire everything together in index.py
11. Test script
12. Git + Vercel deployment config

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

## SKILL 3: Supabase Client

### api/supabase_client.py
```python
from supabase import create_client
from api.config import SUPABASE_URL, SUPABASE_SERVICE_KEY

supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
```

---

## SKILL 4: WhatsApp Client

### api/whatsapp.py
```python
import httpx
from api.config import WHATSAPP_TOKEN, WHATSAPP_PHONE_ID

async def send_message(to: str, message: str):
    url = f"https://graph.facebook.com/v18.0/{WHATSAPP_PHONE_ID}/messages"
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
        return resp.json()

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
```python
from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import PlainTextResponse
from api.config import VERIFY_TOKEN
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
async def receive(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    background_tasks.add_task(process_webhook, body)
    return {"status": "ok"}

async def process_webhook(body: dict):
    try:
        message = parse_message(body)
        if not message:
            return
        await handle_incoming_message(
            customer_phone=message["from"],
            customer_name=message["name"],
            message_body=message["body"]
        )
    except Exception as e:
        print(f"Error processing webhook: {e}")
```

---

## SKILL 6: Conversation Service

### api/conversation.py
```python
import json
from api.supabase_client import supabase

async def get_conversation(phone: str) -> list:
    """Get conversation history for a customer"""
    result = supabase.table("conversations").select("*").eq("customer_phone", phone).execute()
    if result.data:
        return result.data[0].get("messages", [])
    return []

async def save_conversation(phone: str, name: str, messages: list):
    """Upsert conversation history — keep last 20 messages"""
    trimmed = messages[-20:] if len(messages) > 20 else messages
    supabase.table("conversations").upsert({
        "customer_phone": phone,
        "customer_name": name,
        "messages": json.dumps(trimmed),
        "last_message_at": "now()"
    }, on_conflict="customer_phone").execute()
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

async def save_appointment(data: dict) -> dict:
    """Save appointment to Supabase"""
    result = supabase.table("appointments").insert({
        "customer_name": data["customer_name"],
        "customer_phone": data["customer_phone"],
        "service": data["service_name"],
        "appointment_date": data["date"],
        "start_time": data["start_time"],
        "end_time": data.get("end_time", ""),
        "duration_minutes": data["duration_minutes"],
        "price": data["price"],
        "google_event_id": data.get("google_event_id", ""),
        "status": "confirmed"
    }).execute()
    return result.data[0] if result.data else {}
```

---

## SKILL 10: AI Agent (Gemini with Tool Use)

### api/ai_agent.py
This is the brain. It must:

1. Load conversation history from Supabase
2. Build system prompt with services, hours, current date
3. Call Gemini with conversation + tools
4. If Gemini returns function_call → execute the tool → feed result back → get final response
5. Send final text to customer via WhatsApp
6. Save updated conversation to Supabase

### Tool execution:
```python
async def execute_tool(tool_name: str, args: dict) -> str:
    if tool_name == "check_calendar_availability":
        slots = find_available_slots(args["date"], args["duration_minutes"])
        if not slots:
            return f"No hay horarios disponibles para {args['date']}."
        return f"Horarios disponibles para {args['date']}: {', '.join(slots)}"

    elif tool_name == "create_appointment":
        # Create calendar event
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
        # Save to Supabase
        end_minutes = int(args["start_time"].split(":")[0]) * 60 + \
                      int(args["start_time"].split(":")[1]) + args["duration_minutes"]
        end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"

        await save_appointment({
            **args,
            "end_time": end_time,
            "google_event_id": event_id
        })
        return f"Cita creada exitosamente. Evento ID: {event_id}"

    return "Herramienta no reconocida."
```

---

## SKILL 11: Main Entry Point

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

## SKILL 12: GitHub + Vercel Deployment

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

## ERROR HANDLING PATTERNS

- Wrap ALL webhook processing in try/except
- Log errors with full traceback using print() (Vercel captures stdout)
- Send friendly error message to customer: "⚠️ Hubo un error. Por favor intenta de nuevo."
- Never let Gemini API errors crash the webhook
- If Google Calendar fails, tell customer "No pude verificar disponibilidad, intenta en unos minutos."
- If Supabase fails, still try to respond via WhatsApp with a generic message

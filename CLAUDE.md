# CLAUDE.md — Noduz WhatsApp Booking Bot

## PROJECT IDENTITY

- **Name:** Noduz WhatsApp Booking Bot-Barbershop
- **Purpose:** AI-powered WhatsApp chatbot for appointment scheduling (barbershops, restaurants, corporate)
- **Stack:** Python (FastAPI) + Supabase (PostgreSQL + Auth) + Vercel (serverless deployment) + GitHub (version control + CI/CD)
- **AI Model:** Google Gemini Flash (free tier) via google-genai SDK
- **WhatsApp:** Meta Cloud API (direct integration, no N8N)
- **Calendar:** Google Calendar API for availability checks and event creation
- **Deployment:** Push to GitHub → Vercel auto-deploys → Meta webhook points to Vercel URL
- **No ngrok needed** — Vercel gives you a permanent public HTTPS URL

---

## ARCHITECTURE

```
Customer sends WhatsApp message
        │
        ▼
Meta Cloud API → POST webhook → Vercel (FastAPI serverless function)
        │
        ▼
   Parse message → Identify customer
        │
        ▼
   Load conversation history from Supabase
        │
        ▼
   Send to Gemini AI with system prompt + tools
        │
        ▼
   AI decides: check calendar? create event? save appointment?
        │
        ▼
   Execute tool calls → Google Calendar API / Supabase
        │
        ▼
   Send AI response back via WhatsApp API
        │
        ▼
   Save conversation to Supabase
```

---

## DIRECTORY STRUCTURE — CREATE EXACTLY THIS

```
noduz-whatsapp-bot/
├── CLAUDE.md
├── SKILLS.md
├── .env.example
├── .gitignore
├── requirements.txt
├── vercel.json
├── api/
│   ├── __init__.py
│   ├── index.py              # Main entry point — Vercel serverless function
│   ├── webhook.py             # GET (verify) + POST (receive messages) handlers
│   ├── whatsapp.py            # WhatsApp Cloud API client (send messages)
│   ├── ai_agent.py            # Gemini AI agent with tool calling
│   ├── calendar_service.py    # Google Calendar API (check availability, create events)
│   ├── supabase_client.py     # Supabase client initialization
│   ├── conversation.py        # Conversation history CRUD (Supabase)
│   ├── appointments.py        # Appointment CRUD (Supabase)
│   ├── config.py              # Environment variables and settings
│   └── date_parser.py         # Spanish date parsing utility
├── scripts/
│   ├── setup_supabase.sql     # SQL to create all Supabase tables
│   └── test_conversation.py   # Local test script to simulate conversation
└── tests/
    ├── test_webhook.py
    ├── test_ai_agent.py
    └── test_calendar.py
```

---

## VERCEL CONFIGURATION

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
    {
      "src": "/webhook",
      "dest": "api/index.py"
    },
    {
      "src": "/health",
      "dest": "api/index.py"
    }
  ]
}
```

### api/index.py — Vercel Entry Point
This file must expose a FastAPI app that Vercel can serve as a serverless function:

```python
from fastapi import FastAPI
from api.webhook import router as webhook_router

app = FastAPI(title="Noduz WhatsApp Bot")
app.include_router(webhook_router)

@app.get("/health")
async def health():
    return {"status": "ok", "service": "noduz-whatsapp-bot"}
```

---

## SUPABASE DATABASE SCHEMA

### Run this SQL in Supabase SQL Editor (scripts/setup_supabase.sql):

```sql
-- Conversations table: tracks chat state per customer
CREATE TABLE conversations (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_phone TEXT NOT NULL,
    customer_name TEXT DEFAULT 'Cliente',
    messages JSONB DEFAULT '[]'::jsonb,
    last_message_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(customer_phone)
);

-- Appointments table: all confirmed bookings
CREATE TABLE appointments (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    customer_name TEXT NOT NULL,
    customer_phone TEXT NOT NULL,
    service TEXT NOT NULL,
    appointment_date DATE NOT NULL,
    start_time TIME NOT NULL,
    end_time TIME NOT NULL,
    duration_minutes INTEGER NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    currency TEXT DEFAULT 'MXN',
    google_event_id TEXT,
    status TEXT DEFAULT 'confirmed',
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Businesses table (for multi-tenant future)
CREATE TABLE businesses (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    name TEXT NOT NULL,
    business_type TEXT NOT NULL,
    whatsapp_phone_id TEXT UNIQUE NOT NULL,
    whatsapp_token TEXT NOT NULL,
    google_calendar_id TEXT DEFAULT 'primary',
    google_credentials_json TEXT,
    timezone TEXT DEFAULT 'America/Mexico_City',
    business_start_hour INTEGER DEFAULT 9,
    business_end_hour INTEGER DEFAULT 20,
    services JSONB DEFAULT '[]'::jsonb,
    ai_system_prompt TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Enable Row Level Security
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE appointments ENABLE ROW LEVEL SECURITY;
ALTER TABLE businesses ENABLE ROW LEVEL SECURITY;

-- Allow service role full access
CREATE POLICY "Service role full access" ON conversations FOR ALL USING (true);
CREATE POLICY "Service role full access" ON appointments FOR ALL USING (true);
CREATE POLICY "Service role full access" ON businesses FOR ALL USING (true);

-- Indexes for performance
CREATE INDEX idx_conversations_phone ON conversations(customer_phone);
CREATE INDEX idx_appointments_date ON appointments(appointment_date);
CREATE INDEX idx_appointments_phone ON appointments(customer_phone);
```

---

## WEBHOOK HANDLERS

### GET /webhook — Meta Verification
```python
@router.get("/webhook")
async def verify_webhook(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    if mode == "subscribe" and token == config.VERIFY_TOKEN:
        return PlainTextResponse(content=challenge)
    return PlainTextResponse(content="Forbidden", status_code=403)
```

### POST /webhook — Receive Messages
```python
@router.post("/webhook")
async def receive_message(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()

    # Always return 200 immediately — Meta retries otherwise
    background_tasks.add_task(process_message, body)
    return {"status": "ok"}
```

---

## WHATSAPP API CLIENT

### Send text message:
```python
import httpx

async def send_whatsapp_message(phone_id: str, token: str, to: str, message: str):
    url = f"https://graph.facebook.com/v18.0/{phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message}
    }
    async with httpx.AsyncClient() as client:
        response = await client.post(url, json=payload, headers=headers)
        return response.json()
```

### Parse incoming message:
```python
def parse_whatsapp_message(body: dict):
    entry = body.get("entry", [{}])[0]
    changes = entry.get("changes", [{}])[0]
    value = changes.get("value", {})

    messages = value.get("messages", [])
    if not messages or messages[0].get("type") != "text":
        return None

    return {
        "phone_number_id": value.get("metadata", {}).get("phone_number_id", ""),
        "from": messages[0].get("from", ""),
        "name": value.get("contacts", [{}])[0].get("profile", {}).get("name", "Cliente"),
        "body": messages[0].get("text", {}).get("body", "").strip()
    }
```

---

## AI AGENT WITH GEMINI

### Tool Definitions:
```python
tools = [
    {
        "name": "check_calendar_availability",
        "description": "Check available time slots on the calendar for a specific date. Always use before offering times.",
        "parameters": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "duration_minutes": {"type": "integer", "description": "Service duration in minutes"}
            },
            "required": ["date", "duration_minutes"]
        }
    },
    {
        "name": "create_appointment",
        "description": "Create a confirmed appointment. Only call after explicit customer confirmation.",
        "parameters": {
            "type": "object",
            "properties": {
                "customer_name": {"type": "string"},
                "customer_phone": {"type": "string"},
                "service_name": {"type": "string"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "start_time": {"type": "string", "description": "HH:MM"},
                "duration_minutes": {"type": "integer"},
                "price": {"type": "number"}
            },
            "required": ["customer_name", "customer_phone", "service_name", "date", "start_time", "duration_minutes", "price"]
        }
    }
]
```

### System Prompt:
The AI agent must use the following Spanish system prompt. The system prompt is dynamically built using data from CLIENT_PROFILE.md (business name, services, hours, tone) but the structure and rules below must always be included. Here is the full template:

"""
Eres el asistente virtual de {business_name}. Tu trabajo es ayudar a los clientes a agendar citas de forma natural, amigable y conversacional. SIEMPRE responde en español.

## SERVICIOS DISPONIBLES

{dynamically loaded from config.py — example format:}
- Corte de cabello: 30 minutos, $150 MXN
- Corte + Barba: 45 minutos, $250 MXN
- Solo Barba: 20 minutos, $100 MXN
- Corte + Barba + Cejas: 60 minutos, $300 MXN
- Tratamiento capilar: 45 minutos, $350 MXN

## HORARIO DE TRABAJO

- Días laborales: {from config — e.g., Lunes a Sábado}
- Horario: {from config — e.g., 9:00 AM a 8:00 PM}
- Cerrado: {from config — e.g., Domingo}
- Zona horaria: {from config — e.g., America/Mexico_City}

## CÓMO DEBES COMPORTARTE

1. Saluda al cliente de forma cálida y natural. NO uses menús numerados rígidos. Conversa como lo haría una recepcionista amigable en persona.
2. Si el cliente no ha dicho qué servicio quiere, pregúntale de forma conversacional. Puedes mencionar los servicios de forma natural dentro de la conversación, nunca como lista numerada.
3. Cuando el cliente elija un servicio (puede decirlo de muchas formas: "quiero un corte", "la barba", "todo completo", "lo de siempre", etc.), confírmale el servicio y pregúntale para qué día le gustaría.
4. Cuando el cliente diga una fecha (puede decir "mañana", "el viernes", "15 de marzo", "hoy", "pasado mañana", "la próxima semana", etc.), usa la herramienta check_calendar_availability para buscar los horarios disponibles para ese día.
5. Con los horarios disponibles, preséntaselos de forma conversacional. Por ejemplo: "Tengo espacio a las 10, a las 11:30, y en la tarde a las 3 y las 4:30, cuál te queda mejor?" NO muestres todos los slots, selecciona las mejores 4-6 opciones distribuidas entre mañana y tarde.
6. Cuando el cliente elija un horario, muéstrale un resumen completo de la cita y pide confirmación explícita.
7. SOLO cuando el cliente confirme explícitamente ("sí", "dale", "perfecto", "confírmame", "va", "órale", "sí, está bien"), usa la herramienta create_appointment para crear la cita.
8. Después de crear la cita, envía el mensaje de confirmación con todos los detalles.

## CÓMO INTERPRETAR FECHAS

- "hoy" = {current_date}
- "mañana" = fecha de hoy + 1 día
- "pasado mañana" = fecha de hoy + 2 días
- "el lunes", "el martes", etc. = el próximo día con ese nombre
- "la próxima semana" = el lunes de la siguiente semana
- "DD/MM/AAAA" o "DD-MM-AAAA" = fecha directa
- Fecha de hoy: {current_date_spanish} ({current_date_iso})
- Día de la semana: {current_day_name}

## REGLAS QUE NUNCA PUEDES ROMPER

- NUNCA inventes horarios disponibles. SIEMPRE usa la herramienta check_calendar_availability antes de ofrecer cualquier horario.
- NUNCA crees una cita sin que el cliente haya confirmado explícitamente.
- Si no hay disponibilidad para el día solicitado, sugiere amablemente otro día cercano.
- No agendes en días no laborales.
- No agendes en fechas pasadas. Si el cliente pide una fecha que ya pasó, dile amablemente que elija una fecha futura.
- Los horarios deben estar dentro del horario laboral. El último turno posible es la hora de cierre MENOS la duración del servicio.
- Si el cliente pregunta algo que no tiene que ver con agendar una cita, responde brevemente de forma amable y redirige la conversación hacia el agendamiento.
- Si el cliente quiere cancelar durante el proceso, responde amablemente y ofrece agendar en otro momento.
- Si el cliente envía un mensaje confuso o que no entiendes, pide aclaración de forma natural sin sonar como un robot.
- NUNCA menciones que eres una inteligencia artificial, un bot, o un sistema automatizado. Compórtate como si fueras una persona real atendiendo en la recepción.

## FORMATO DE CONFIRMACIÓN

Cuando la cita esté confirmada exitosamente, envía exactamente este formato:

Tu cita ha sido confirmada.

Servicio: {nombre del servicio}
Fecha: {fecha en formato legible en español, ejemplo: Viernes 21 de marzo de 2026}
Hora: {hora inicio} - {hora fin}
Precio: ${precio} MXN

{post_confirmation_message from CLIENT_PROFILE.md — example: "Te esperamos, no olvides llegar 5 minutos antes."}

{cancellation_policy from CLIENT_PROFILE.md — example: "Si necesitas cancelar, avísanos con al menos 2 horas de anticipación."}

## INFORMACIÓN ADICIONAL DEL NEGOCIO

{Any extra context from CLIENT_PROFILE.md: address, parking info, special instructions, things to always mention, things to never discuss}
"""

### How to build this prompt in code:

The system prompt must be assembled dynamically in ai_agent.py by:
1. Loading business name, services, hours, and tone from config.py
2. Calculating current date, day name, and ISO date at runtime using America/Mexico_City timezone
3. Injecting the post-confirmation message and cancellation policy from config
4. Injecting any additional business context from config
5. The final prompt string is passed to Gemini as the system_instruction parameter

### Key implementation rules:
- Services list must come from config.py (loaded from CLIENT_PROFILE.md data), NEVER hardcoded in the prompt
- Current date must be calculated at the moment the message is processed, not at deployment time
- The tone and personality must match what the client described in Step 0.5
- If the client said "casual and fun", the greeting and overall tone should reflect that
- If the client said "professional", keep it formal but warm

### Gemini API Call with Tool Use:
```python
from google import genai

client = genai.Client(api_key=config.GEMINI_API_KEY)

response = client.models.generate_content(
    model="gemini-2.0-flash",
    contents=conversation_history,
    config={
        "system_instruction": system_prompt,
        "tools": tool_definitions
    }
)
```

When Gemini returns a function_call, execute the tool (calendar check or appointment creation), feed the result back, and get the final text response.

---

## GOOGLE CALENDAR INTEGRATION

### Check Availability:
1. Fetch events for requested date (9AM-8PM)
2. Build busy blocks from events
3. Find free slots in 30-minute increments considering service duration
4. Return list of available time strings

### Create Event:
1. Title: "✂️ {service} - {customer_name}"
2. Description: customer details, service, price
3. Timezone: America/Mexico_City
4. 30-minute popup reminder
5. Return event ID

### Authentication:
Use a Google Service Account. Store the service account JSON in Supabase or as a Vercel environment variable (base64-encoded).

---

## ENVIRONMENT VARIABLES (.env.example)

```env
# WhatsApp
WHATSAPP_TOKEN=EAAxxxxxxx
WHATSAPP_PHONE_ID=987895124414898
VERIFY_TOKEN=noduz2026

# Meta App
APP_SECRET=your_app_secret

# Supabase
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJxxxxxxx

# Gemini AI
GEMINI_API_KEY=AIzaxxxxxxx

# Google Calendar
GOOGLE_CALENDAR_ID=primary
GOOGLE_SERVICE_ACCOUNT_JSON=base64_encoded_json_here

# App
TIMEZONE=America/Mexico_City
```

---

## STEP 0 — COLLECT ALL API KEYS (DO THIS FIRST)

Before writing ANY code, ask the user for each of these keys ONE BY ONE. After collecting all of them, create a file called `SECRETS.md` in the project root with all the values. This file is gitignored so it won't be pushed to GitHub. Also use these values to populate the `.env` file automatically.

### Keys to collect (ask the user for each):

1. **WHATSAPP_TOKEN** — "What is your WhatsApp access token? (starts with EAA... — get it from Meta → WhatsApp → API Setup → Generate token)"
2. **WHATSAPP_PHONE_ID** — "What is your WhatsApp Phone Number ID? (found in Meta → WhatsApp → API Setup, example: 987895124414898)"
3. **APP_SECRET** — "What is your Meta App Secret? (found in Meta → Settings → Basic → App Secret)"
4. **VERIFY_TOKEN** — "What verify token do you want to use for the webhook? (any word you choose, like 'noduz2026')"
5. **SUPABASE_URL** — "What is your Supabase project URL? (found in Supabase → Settings → API, example: https://xxxxx.supabase.co)"
6. **SUPABASE_SERVICE_KEY** — "What is your Supabase service_role key? (found in Supabase → Settings → API → service_role, starts with eyJ...)"
7. **GEMINI_API_KEY** — "What is your Gemini API key? (get it from aistudio.google.com/apikey, starts with AIza...)"
8. **GOOGLE_CALENDAR_ID** — "What is the Google Calendar ID to use? (usually your email or 'primary')"
9. **GOOGLE_SERVICE_ACCOUNT_JSON** — "Paste the contents of your Google Service Account JSON file (or provide the file path and I'll read it)"

### After collecting all keys, create these files:

#### SECRETS.md (gitignored — user's private reference)
```markdown
# 🔐 NODUZ API KEYS — DO NOT SHARE THIS FILE

## WhatsApp
- Token: [value]
- Phone ID: [value]
- App Secret: [value]
- Verify Token: [value]

## Supabase
- URL: [value]
- Service Key: [value]

## Google
- Gemini API Key: [value]
- Calendar ID: [value]
- Service Account: [saved to google-credentials.json]

## Vercel Deployment URL
- URL: (fill after deployment)

## Meta Webhook
- Callback URL: (Vercel URL + /webhook)
- Verify Token: [same as above]
```

#### .env (gitignored — used by the app)
Populate with all the collected values.

#### google-credentials.json (gitignored — if service account JSON was provided)
Save the Google Service Account JSON here. Also create a base64-encoded version for the GOOGLE_SERVICE_ACCOUNT_JSON env var.

### Add to .gitignore:
```
SECRETS.md
.env
google-credentials.json
```

### IMPORTANT:
- NEVER commit SECRETS.md, .env, or google-credentials.json to git
- ALWAYS confirm with the user before storing any key
- If the user doesn't have a key yet, tell them exactly where to get it with the URL
- After all keys are collected, proceed to Step 0.5

---

## STEP 0.5 — CLIENT CONTEXT & BUSINESS PROFILE (DO THIS AFTER KEYS)

After collecting all API keys, ask the user the following questions to understand the client's business. Store the answers in a file called `CLIENT_PROFILE.md` in the project root (gitignored). Use this information to customize the system prompt, services catalog, and bot behavior.

### Questions to ask (one by one):

**Business Identity:**
1. "What is the name of the business?" (e.g., "Barbería Don Pepe")
2. "What type of business is it?" (barbershop / restaurant / clinic / salon / corporate / other)
3. "What city and country is the business located in?" (e.g., "Monterrey, México")
4. "Does the business have an address customers need to know?" (optional)

**Services & Pricing:**
5. "List all the services offered with their duration in minutes and price. Example: Corte de cabello, 30 min, $150 MXN" (collect each service one by one until the user says done)

**Schedule:**
6. "What are the working days?" (e.g., "Lunes a Sábado")
7. "What is the opening time?" (e.g., "9:00 AM")
8. "What is the closing time?" (e.g., "8:00 PM")
9. "Are there any break hours? Like a lunch break?" (e.g., "No" or "2:00 PM to 3:00 PM")

**Staff:**
10. "How many people take appointments? Just one or multiple?" (if multiple, ask for each person's name and their Google Calendar ID)

**Bot Personality:**
11. "How should the bot talk? Casual and friendly? Professional? Fun with emojis? Give me an example of how you'd want it to greet a customer." (e.g., "¡Qué onda! Bienvenido a Don Pepe 💈" vs "Buenos días, bienvenido a nuestra barbería")
12. "Is there anything the bot should NEVER talk about or always mention?" (e.g., "Always mention we have parking" or "Never discuss competitor prices")
13. "Should the bot ask for any extra info from the customer? Like a specific barber preference, or any notes?" (optional)

**Policies:**
14. "Is there a cancellation policy?" (e.g., "Cancel at least 2 hours before" or "No cancellation policy")
15. "Is there a deposit or advance payment required?" (e.g., "No" or "$50 MXN deposit via transfer")
16. "Any message you want the bot to send AFTER confirming the appointment?" (e.g., "Don't forget to arrive 5 minutes early!")

**Language:**
17. "What language should the bot speak?" (default: Spanish / can be English or bilingual)

### After collecting all answers, create:

#### CLIENT_PROFILE.md (gitignored — reference document)
```markdown
# 📋 CLIENT PROFILE — [Business Name]

## Business
- Name: [value]
- Type: [value]
- Location: [value]
- Address: [value]

## Services
| Service | Duration | Price |
|---------|----------|-------|
| [name]  | [X] min  | $[X] MXN |
| ...     | ...      | ...   |

## Schedule
- Working days: [value]
- Hours: [opening] - [closing]
- Break: [value or "None"]

## Staff
- [Name] — Calendar ID: [value]
- (or "Single operator" if just one person)

## Bot Personality
- Tone: [casual/professional/fun]
- Greeting example: [value]
- Must always mention: [value or "Nothing specific"]
- Must never discuss: [value or "Nothing specific"]
- Extra info to collect: [value or "None"]

## Policies
- Cancellation: [value]
- Deposit: [value]
- Post-confirmation message: [value]

## Language
- Primary: [value]
```

### Then use CLIENT_PROFILE.md to:

1. **Customize config.py** — Set the SERVICES list, business hours, timezone, working days from the profile
2. **Build the system prompt in ai_agent.py** — Inject the business name, services, schedule, tone, policies, and any special instructions directly into the Gemini system prompt
3. **Customize confirmation messages** — Use the post-confirmation message and cancellation policy in the bot's responses
4. **Handle multi-staff** — If there are multiple staff members, the bot should ask "¿Con quién prefieres tu cita?" and check the correct calendar

### Add to .gitignore:
```
CLIENT_PROFILE.md
```

### IMPORTANT:
- The system prompt is the HEART of the bot — it must reflect the client's personality, not a generic template
- If the user provides a greeting example, the bot should match that energy and tone
- Services, prices, and hours should NEVER be hardcoded in the system prompt — they should be loaded from config.py which reads from CLIENT_PROFILE.md data
- This step makes every deployment feel custom-built for the client, which is what justifies the $4,000 MXN implementation fee

---

## DEPLOYMENT FLOW

### First time:
1. Create GitHub repo: `noduz-whatsapp-bot`
2. Push all code to GitHub
3. Go to vercel.com → Import project from GitHub
4. Add all environment variables in Vercel dashboard
5. Deploy — Vercel gives you: `https://noduz-whatsapp-bot.vercel.app`
6. Go to Meta → WhatsApp → Configuration → Webhook:
   - URL: `https://noduz-whatsapp-bot.vercel.app/webhook`
   - Verify Token: `noduz2026`
7. Subscribe to "messages" webhook field
8. Send a test message — bot should respond

### Updates:
1. Make changes locally
2. `git push` to GitHub
3. Vercel auto-deploys in ~30 seconds
4. No downtime, no ngrok, no Docker restarts

---

## CRITICAL RULES

1. **ALL customer messages in Spanish** unless otherwise configured
2. **ALWAYS return 200 OK immediately** on POST webhook — process in background
3. **NEVER hardcode business data** — read from config/environment
4. **ALWAYS check calendar before offering times** — never guess
5. **Phone numbers stored as strings** with country code
6. **All datetimes use America/Mexico_City timezone**
7. **Conversation history limited to last 20 messages** to control token usage
8. **Webhook security:** Validate X-Hub-Signature-256 header using APP_SECRET
9. **Error handling:** Never let exceptions crash the webhook — log and send friendly error to customer
10. **Vercel function timeout:** 60 seconds max — keep Gemini calls efficient

---

## END OF SESSION — REQUIRED LAST STEP

At the end of every Claude Code session, before closing, **update `MEMORY.md`** with a new dated section covering:

1. **Architecture decisions** — any choices made and the reasoning behind them
2. **DB changes** — new tables, columns, migrations, index changes
3. **Code changes** — which files were modified and what changed
4. **New files created** — purpose of each
5. **Bugs fixed** — what broke and how it was solved
6. **Pending / next steps** — anything left to do or follow up on

Format:
```markdown
## Session N — YYYY-MM-DD

### Architecture decisions
...

### DB changes
...

### Code changes
...

### New files
...

### Bugs fixed
...

### Pending
...
```

This file is the project's memory. Future sessions should read it first to understand what has already been built and decided.

---

## WHAT SUCCESS LOOKS LIKE

1. `git push` deploys to Vercel automatically
2. Meta webhook verification succeeds on first try
3. Customer sends "Hola" → bot greets naturally and asks about services
4. Customer says "quiero un corte para mañana" → bot checks calendar, shows times
5. Customer picks a time → bot shows summary, asks confirmation
6. Customer confirms → calendar event created, appointment saved to Supabase, confirmation sent
7. All data visible in Supabase dashboard
8. No ngrok, no Docker, no server management
9. Adding a new business = inserting a row in the businesses table

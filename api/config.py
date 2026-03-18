import os
from dotenv import load_dotenv

load_dotenv()

# WhatsApp
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_ID = os.getenv("WHATSAPP_PHONE_ID", "")
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN", "Noduz2026").strip()
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

# Business info — Family Barber
BUSINESS_NAME = "Family Barber"
BUSINESS_TYPE = "barbershop"
BUSINESS_LOCATION = "San Luis Potosí, México"

BARBERS = ["Daniel", "Enrique", "Juan", "Pedro"]

SERVICES = [
    {"name": "Corte de cabello", "duration": 45, "price": 200},
    {"name": "Corte y barba",    "duration": 80, "price": 300},
    {"name": "Barba",            "duration": 45, "price": 150},
]

WORKING_DAYS = "Lunes a Domingo"
BUSINESS_START_HOUR = 11      # 11:00 AM
BUSINESS_END_HOUR = 20        # 8:00 PM
BREAK_START_HOUR = 14         # 2:00 PM
BREAK_END_HOUR = 16           # 4:00 PM
SLOT_INCREMENT = 30           # minutes between slot options

BOT_GREETING_EXAMPLE = "Que onda! En que te puedo ayudar?"
BOT_LANGUAGE = "Spanish (bilingual — switch to English if customer writes in English)"
CANCELLATION_POLICY = "Si necesitas cancelar, avísanos con al menos 1 hora de anticipación."
POST_CONFIRMATION_MESSAGE = "No se te olvide llegar 5 minutos antes!"
DEPOSIT_REQUIRED = False

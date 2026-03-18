from fastapi import FastAPI
from api.webhook import router

app = FastAPI(title="Noduz WhatsApp Bot — Family Barber")
app.include_router(router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "noduz-whatsapp-bot", "business": "Family Barber"}


@app.get("/")
async def root():
    return {"message": "Noduz WhatsApp Booking Bot is running"}

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from api.webhook import router as webhook_router
from api.dashboard import router as dashboard_router

app = FastAPI(title="Noduz WhatsApp Bot — Family Barber")
app.include_router(webhook_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "noduz-whatsapp-bot", "business": "Family Barber"}


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")

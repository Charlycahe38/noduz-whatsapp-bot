import hashlib
import hmac
import traceback

from fastapi import APIRouter, Request, BackgroundTasks
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
async def receive(request: Request, background_tasks: BackgroundTasks):
    # Validate X-Hub-Signature-256
    if APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        body_bytes = await request.body()
        expected = "sha256=" + hmac.new(
            APP_SECRET.encode(), body_bytes, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return PlainTextResponse(content="Invalid signature", status_code=403)
        body = __import__("json").loads(body_bytes)
    else:
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
        print(f"Error processing webhook: {e}\n{traceback.format_exc()}")

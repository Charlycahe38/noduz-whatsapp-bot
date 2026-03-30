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

    # Validate X-Hub-Signature-256
    if APP_SECRET:
        signature = request.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(
            APP_SECRET.encode(), body_bytes, hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            print(f"[webhook] Invalid signature. Got: {signature[:30]}... Expected: {expected[:30]}...")
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
        print(f"[webhook] Error processing message: {e}\n{traceback.format_exc()}")

    return {"status": "ok"}

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

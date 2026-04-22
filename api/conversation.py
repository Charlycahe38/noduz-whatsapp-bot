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
    """Upsert conversation history — keep last 20 messages."""
    client_id = get_client_id()
    trimmed = messages[-20:] if len(messages) > 20 else messages
    record = {
        "client_id": client_id,
        "customer_phone": phone,
        "customer_name": name,
        "messages": trimmed,
        "last_message_at": datetime.now(timezone.utc).isoformat(),
    }
    supabase.table("conversations").upsert(record, on_conflict="client_id,customer_phone").execute()

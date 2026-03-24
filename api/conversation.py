import json
from api.supabase_client import supabase
from api.config import CLIENT_ID


async def get_conversation(phone: str) -> list:
    """Get conversation history for a customer scoped to this client."""
    query = supabase.table("conversations").select("*").eq("customer_phone", phone)
    if CLIENT_ID:
        query = query.eq("client_id", CLIENT_ID)
    result = query.execute()
    if result.data:
        messages = result.data[0].get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        return messages
    return []


async def save_conversation(phone: str, name: str, messages: list):
    """Upsert conversation history — keep last 20 messages."""
    trimmed = messages[-20:] if len(messages) > 20 else messages
    record = {
        "customer_phone": phone,
        "customer_name": name,
        "messages": json.dumps(trimmed),
        "last_message_at": "now()"
    }
    if CLIENT_ID:
        record["client_id"] = CLIENT_ID
    conflict_cols = "client_id,customer_phone" if CLIENT_ID else "customer_phone"
    supabase.table("conversations").upsert(record, on_conflict=conflict_cols).execute()

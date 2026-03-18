import json
from api.supabase_client import supabase


async def get_conversation(phone: str) -> list:
    """Get conversation history for a customer."""
    result = supabase.table("conversations").select("*").eq("customer_phone", phone).execute()
    if result.data:
        messages = result.data[0].get("messages", [])
        if isinstance(messages, str):
            messages = json.loads(messages)
        return messages
    return []


async def save_conversation(phone: str, name: str, messages: list):
    """Upsert conversation history — keep last 20 messages."""
    trimmed = messages[-20:] if len(messages) > 20 else messages
    supabase.table("conversations").upsert({
        "customer_phone": phone,
        "customer_name": name,
        "messages": json.dumps(trimmed),
        "last_message_at": "now()"
    }, on_conflict="customer_phone").execute()

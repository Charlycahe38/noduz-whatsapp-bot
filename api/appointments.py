from api.supabase_client import supabase
from api.config import CLIENT_ID


async def save_appointment(data: dict) -> dict:
    """Save appointment to Supabase."""
    record = {
        "customer_name": data["customer_name"],
        "customer_phone": data["customer_phone"],
        "service": data["service_name"],
        "appointment_date": data["date"],
        "start_time": data["start_time"],
        "end_time": data.get("end_time", ""),
        "duration_minutes": data["duration_minutes"],
        "price": data["price"],
        "google_event_id": data.get("google_event_id", ""),
        "notes": data.get("barber", ""),
        "status": "confirmed"
    }
    if CLIENT_ID:
        record["client_id"] = CLIENT_ID
    result = supabase.table("appointments").insert(record).execute()
    return result.data[0] if result.data else {}

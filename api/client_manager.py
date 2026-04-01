"""
client_manager.py — Resolves the CLIENT_ID UUID for this deployment.

Priority:
  1. CLIENT_ID env var (fastest, set this in Vercel for production)
  2. Look up by WHATSAPP_PHONE_ID in the clients table (auto-discovery)
  3. Insert a new client row seeded from config.py values (first-run setup)

The result is cached in _client_id_cache so only one DB round-trip per cold start.
"""

import json
import os

_client_id_cache: str | None = None


def get_client_id() -> str:
    """Return the UUID of this deployment's client row. Raises if unresolvable."""
    global _client_id_cache
    if _client_id_cache:
        return _client_id_cache

    # 1. Explicit env var — fastest path, use in production Vercel
    env_id = os.getenv("CLIENT_ID", "").strip()
    if env_id:
        _client_id_cache = env_id
        print(f"[client_manager] CLIENT_ID from env: {_client_id_cache}")
        return _client_id_cache

    # 2. Look up by WHATSAPP_PHONE_ID — avoids having to copy UUID manually
    from api.supabase_client import supabase
    from api.config import WHATSAPP_PHONE_ID

    result = supabase.table("clients").select("id").eq("whatsapp_phone_id", WHATSAPP_PHONE_ID).execute()
    if result.data:
        _client_id_cache = result.data[0]["id"]
        print(f"[client_manager] CLIENT_ID resolved from DB: {_client_id_cache}")
        return _client_id_cache

    # 3. First run — create the client row from config values
    from api.config import (
        WHATSAPP_TOKEN, VERIFY_TOKEN, APP_SECRET,
        BUSINESS_NAME, BUSINESS_TYPE, BUSINESS_LOCATION,
        GEMINI_API_KEY, GOOGLE_CALENDAR_ID, GOOGLE_SERVICE_ACCOUNT_JSON,
        TIMEZONE, WORKING_DAYS, BUSINESS_START_HOUR, BUSINESS_END_HOUR,
        BREAK_START_HOUR, BREAK_END_HOUR, SLOT_INCREMENT,
        SERVICES, BARBERS, BOT_LANGUAGE, BOT_GREETING_EXAMPLE,
        CANCELLATION_POLICY, POST_CONFIRMATION_MESSAGE, DEPOSIT_REQUIRED,
    )

    record = {
        "business_name": BUSINESS_NAME,
        "business_type": BUSINESS_TYPE,
        "business_location": BUSINESS_LOCATION,
        "whatsapp_phone_id": WHATSAPP_PHONE_ID,
        "whatsapp_token": WHATSAPP_TOKEN,
        "verify_token": VERIFY_TOKEN,
        "app_secret": APP_SECRET,
        "gemini_api_key": GEMINI_API_KEY,
        "google_calendar_id": GOOGLE_CALENDAR_ID,
        "google_service_account_json": GOOGLE_SERVICE_ACCOUNT_JSON,
        "timezone": TIMEZONE,
        "working_days": WORKING_DAYS,
        "business_start_hour": BUSINESS_START_HOUR,
        "business_end_hour": BUSINESS_END_HOUR,
        "break_start_hour": BREAK_START_HOUR,
        "break_end_hour": BREAK_END_HOUR,
        "slot_increment": SLOT_INCREMENT,
        "services": SERVICES,
        "barbers": BARBERS,
        "bot_language": BOT_LANGUAGE,
        "bot_greeting": BOT_GREETING_EXAMPLE,
        "cancellation_policy": CANCELLATION_POLICY,
        "post_confirmation_message": POST_CONFIRMATION_MESSAGE,
        "deposit_required": DEPOSIT_REQUIRED,
    }

    create_result = supabase.table("clients").insert(record).execute()
    if not create_result.data:
        raise RuntimeError("[client_manager] Failed to create client row in Supabase")

    _client_id_cache = create_result.data[0]["id"]
    print(f"[client_manager] Created new client row: {_client_id_cache} — add CLIENT_ID={_client_id_cache} to your .env and Vercel env vars to skip this step.")
    return _client_id_cache

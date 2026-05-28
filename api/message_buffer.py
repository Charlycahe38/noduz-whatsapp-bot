"""
message_buffer.py — Per-customer message queue and processing lock.

Why this exists:
  When a customer sends several messages quickly ("Hola", "Quiero corte", "Mañana",
  "Con Daniel"), the webhook fires 4 times. Without coordination, that means 4
  concurrent AI calls for the same customer — confused responses and wasted quota.

  This module provides:
    1. A Supabase-backed message queue: every incoming message is saved immediately.
    2. A per-customer processing lock: only one function instance processes a given
       customer at a time. Others enqueue and return.
    3. A debounce window: the lock holder waits briefly so burst messages accumulate
       before the AI call — turning 4 messages into 1 combined request.

  Because Vercel serverless has NO shared in-process memory between requests, all
  coordination state (queue + locks) must live in Supabase.

Lock lifecycle:
  acquire → debounce sleep → flush messages → call AI → check for more → release
  Stale locks (> LOCK_STALE_AFTER seconds old) are stolen so a crashed function
  never blocks a customer permanently.
"""

from datetime import datetime, timezone, timedelta

from api.supabase_client import supabase
from api.client_manager import get_client_id

DEBOUNCE_SECONDS = 2       # wait this long for a message burst to settle
LOCK_STALE_AFTER = 55      # steal locks older than this (Vercel timeout is 60s)


async def enqueue_message(customer_phone: str, customer_name: str, message_body: str) -> None:
    client_id = get_client_id()
    supabase.table("message_queue").insert({
        "client_id": client_id,
        "customer_phone": customer_phone,
        "customer_name": customer_name,
        "message_body": message_body,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "processed": False,
    }).execute()


async def try_acquire_lock(customer_phone: str) -> bool:
    """
    Atomically acquire the per-customer processing lock.

    Strategy:
      1. UPDATE WHERE processing_lock = FALSE  → atomic test-and-set via Postgres
         row locking. If two functions race, only one UPDATE wins.
      2. If UPDATE matched nothing, check why:
         a. No conversation row yet → INSERT with lock=TRUE (new customer).
         b. Lock is held but stale → steal it.
         c. Lock is held and fresh → return False (someone else is working).

    Returns True if this caller now owns the lock, False otherwise.
    """
    client_id = get_client_id()
    now_iso = datetime.now(timezone.utc).isoformat()

    # Step 1: atomic acquire via conditional UPDATE
    result = (
        supabase.table("conversations")
        .update({"processing_lock": True, "lock_acquired_at": now_iso})
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .eq("processing_lock", False)
        .execute()
    )
    if result.data:
        return True

    # Step 2: UPDATE matched nothing — figure out why
    existing = (
        supabase.table("conversations")
        .select("processing_lock, lock_acquired_at")
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .execute()
    )

    if not existing.data:
        # No conversation row yet (new customer) — create one with the lock held
        try:
            supabase.table("conversations").insert({
                "client_id": client_id,
                "customer_phone": customer_phone,
                "customer_name": "Cliente",
                "messages": [],
                "processing_lock": True,
                "lock_acquired_at": now_iso,
            }).execute()
            return True
        except Exception:
            # Another concurrent function inserted first — we lose the race
            return False

    row = existing.data[0]
    acquired_at_raw = row.get("lock_acquired_at")
    if acquired_at_raw:
        acquired_at = datetime.fromisoformat(acquired_at_raw.replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - acquired_at).total_seconds()
        if age >= LOCK_STALE_AFTER:
            # Lock is stale (function crashed) — steal it
            supabase.table("conversations").update({
                "processing_lock": True,
                "lock_acquired_at": now_iso,
            }).eq("client_id", client_id).eq("customer_phone", customer_phone).execute()
            print(f"[message_buffer] Stale lock stolen for {customer_phone} (age={age:.0f}s)")
            return True

    return False  # lock is fresh, another function is actively processing


async def release_lock(customer_phone: str) -> None:
    client_id = get_client_id()
    supabase.table("conversations").update({
        "processing_lock": False,
        "lock_acquired_at": None,
    }).eq("client_id", client_id).eq("customer_phone", customer_phone).execute()


async def flush_pending_messages(customer_phone: str) -> list[dict]:
    """
    Fetch all unprocessed messages for this customer and mark them processed.
    The lock must be held by the caller before calling this.
    """
    client_id = get_client_id()
    result = (
        supabase.table("message_queue")
        .select("*")
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .eq("processed", False)
        .order("received_at")
        .execute()
    )
    if not result.data:
        return []

    ids = [r["id"] for r in result.data]
    supabase.table("message_queue").update({"processed": True}).in_("id", ids).execute()
    return result.data


async def has_pending_messages(customer_phone: str) -> bool:
    """Check if new messages arrived while the AI was thinking."""
    client_id = get_client_id()
    result = (
        supabase.table("message_queue")
        .select("id")
        .eq("client_id", client_id)
        .eq("customer_phone", customer_phone)
        .eq("processed", False)
        .limit(1)
        .execute()
    )
    return bool(result.data)


def combine_messages(messages: list[dict]) -> str:
    """
    Join multiple messages from a single burst into one text block.
    The AI receives this as a single user turn and handles it naturally.
    Example: ["Hola", "Quiero corte", "Mañana", "Con Daniel"]
             → "Hola\nQuiero corte\nMañana\nCon Daniel"
    """
    bodies = [m["message_body"].strip() for m in messages if m.get("message_body", "").strip()]
    return "\n".join(bodies)

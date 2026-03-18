"""
Local test script — simulates a full booking conversation without WhatsApp.
Run from project root: python scripts/test_conversation.py
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.ai_agent import handle_incoming_message

TEST_PHONE = "5214441234567"
TEST_NAME = "Carlos Test"

CONVERSATION = [
    "Hola, buenas tardes",
    "Quiero un corte de cabello",
    "Con Daniel por favor",
    "Para mañana",
    "A las 11 está bien",
    "Sí, confírmame",
]


async def main():
    print("=" * 60)
    print("Family Barber — Bot Test")
    print("=" * 60)

    for msg in CONVERSATION:
        print(f"\n[CLIENTE] {msg}")
        await handle_incoming_message(TEST_PHONE, TEST_NAME, msg)
        print("-" * 40)
        await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())

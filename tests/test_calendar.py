"""Tests for calendar service utilities."""
# Calendar tests require real credentials — skip in CI
# Run manually after configuring .env
import pytest


@pytest.mark.skip(reason="Requires real Google Calendar credentials")
def test_find_slots():
    from api.calendar_service import find_available_slots
    slots = find_available_slots("2026-03-25", 45)
    assert isinstance(slots, list)


@pytest.mark.skip(reason="Requires real Google Calendar credentials")
def test_create_event():
    from api.calendar_service import create_calendar_event
    event_id = create_calendar_event(
        "Test Event", "Test Description",
        "2026-03-25", "11:00", 45
    )
    assert len(event_id) > 0

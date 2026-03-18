"""Tests for AI agent utilities."""
from api.date_parser import parse_spanish_date
from datetime import date, timedelta


def test_parse_hoy():
    result = parse_spanish_date("hoy")
    assert result == date.today().isoformat()


def test_parse_manana():
    result = parse_spanish_date("mañana")
    assert result == (date.today() + timedelta(days=1)).isoformat()


def test_parse_pasado_manana():
    result = parse_spanish_date("pasado mañana")
    assert result == (date.today() + timedelta(days=2)).isoformat()


def test_parse_date_format():
    result = parse_spanish_date("21/03/2026")
    assert result == "2026-03-21"


def test_parse_invalid():
    result = parse_spanish_date("next month sometime")
    assert result is None

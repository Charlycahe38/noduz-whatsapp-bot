"""Tests for webhook handlers."""
import pytest
from fastapi.testclient import TestClient
from api.index import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_webhook_verify_valid():
    response = client.get("/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "Noduz2026",
        "hub.challenge": "test_challenge_123"
    })
    assert response.status_code == 200
    assert response.text == "test_challenge_123"


def test_webhook_verify_invalid_token():
    response = client.get("/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "wrong_token",
        "hub.challenge": "test_challenge_123"
    })
    assert response.status_code == 403

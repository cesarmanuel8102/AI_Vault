"""DASH-02: test stale/missing dashboard routes."""
import pytest, requests

BASE = "http://127.0.0.1:8090"

def test_utility_status_200():
    r = requests.get(f"{BASE}/brain/utility/status", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "/brain/utility/v2" in data.get("canonical", "")

def test_learning_proposals_200():
    r = requests.get(f"{BASE}/brain/learning/proposals", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert "/brain/chat_excellence/proposals" in data.get("canonical", "")
    assert "items" in data

def test_utility_v2_still_200():
    r = requests.get(f"{BASE}/brain/utility/v2", timeout=10)
    assert r.status_code == 200
    assert "ok" in r.json() or "u_score" in r.json()

def test_utility_governance_status_still_200():
    r = requests.get(f"{BASE}/brain/utility-governance/status", timeout=10)
    assert r.status_code == 200

def test_chat_excellence_proposals_still_200():
    r = requests.get(f"{BASE}/brain/chat_excellence/proposals", timeout=10)
    assert r.status_code == 200
    assert "items" in r.json()

def test_utility_status_includes_canonical():
    r = requests.get(f"{BASE}/brain/utility/status", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data.get("canonical") in ("/brain/utility/v2",)

def test_learning_proposals_includes_items():
    r = requests.get(f"{BASE}/brain/learning/proposals", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("items"), list)

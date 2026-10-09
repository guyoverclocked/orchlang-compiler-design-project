from fastapi.testclient import TestClient

import triage.api as api_module

client = TestClient(api_module.app)

INCIDENT = {
    "incident_id": "API-1",
    "site": "GTS-01",
    "reported_by": "guard",
    "text": "Intruder forced open the loading bay gate overnight; stock appears stolen.",
}


def test_health():
    assert client.get("/health").json()["status"] == "ok"


def test_triage_then_approve_flow():
    submitted = client.post("/triage", json=INCIDENT).json()
    assert submitted["status"] == "pending_approval"
    assert submitted["report"]["classification"]["category"] == "physical_security"

    approved = client.post("/approve/API-1").json()
    assert approved["status"] == "approved"


def test_validation_rejects_short_text():
    bad = dict(INCIDENT, incident_id="API-2", text="too short")
    assert client.post("/triage", json=bad).status_code == 422

"""Journey E: sourced answers, retrieval authorisation, prompt injection, structured advisory output,
graceful failure with the model offline."""
import asyncio
import importlib
import time
import uuid

import jwt
import pytest

from tests.conftest import JWKS, KEY, KID

DA_OFFICE = "00000000-0000-4000-8000-000000000006"          # do-caseworker, RO-DEMO-01 (synthetic seed)


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/ai.db")
    import app.config as config
    import app.infra.db as db
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None
    from app.infra.models import Base
    from app.infra.tables import metadata

    async def setup():
        async with db.engine().begin() as c:
            await c.run_sync(Base.metadata.create_all)
            await c.run_sync(metadata.create_all)
            from epfo_persistence.policy import policy_metadata
            await c.run_sync(policy_metadata.create_all)
        from app import seed
        from pathlib import Path
        seed.SEED_FILE = str(Path(__file__).resolve().parents[3] / "scripts" / "seed" / "synthetic.json")
        await seed.main()
    asyncio.run(setup())
    import epfo_auth
    from fastapi.testclient import TestClient

    from app.api import ai_routes
    from app.ai.provider import DisabledProvider
    monkeypatch.setattr(ai_routes, "provider", DisabledProvider())
    from app.main import create_app
    application = create_app()
    epfo_auth.configure(audience="intelligence-service", jwks=epfo_auth.JwksCache("http://t", fetch=lambda _: JWKS))

    def deliver(event_type, payload):
        from app.api.routes import dispatch
        from epfo_persistence.consumer import apply_once
        asyncio.run(apply_once(db.sessions(), {"event_id": str(uuid.uuid4()), "event_type": event_type,
                                               "correlation_id": "c", "occurred_at": "2026-09-27T10:00:00+00:00",
                                               "payload": payload}, dispatch))
    yield TestClient(application, raise_server_exceptions=False), deliver, ai_routes
    monkeypatch.undo()
    importlib.reload(config)
    db.settings = config.settings
    db._engine = None


def hdr(stakeholder, subject="m-1"):
    now = int(time.time())
    claims = {"iss": "epfo-gateway", "aud": "intelligence-service", "sub": subject, "stakeholder": stakeholder,
              "iat": now, "exp": now + 60, "jti": str(uuid.uuid4()), "correlation_id": str(uuid.uuid4())}
    return {"Authorization": "Bearer " + jwt.encode(claims, KEY, algorithm="EdDSA", headers={"kid": KID})}


def ask(client, question, stakeholder="member", subject="m-1"):
    return client.post("/api/v1/ai/knowledge/search", json={"question": question}, headers=hdr(stakeholder, subject))


class ObeyingModel:
    """A model that does whatever a retrieved document tells it to — the worst case."""
    model_id = "test-obeying-model"

    async def health(self):
        return {"provider": "test", "available": True, "model_id": self.model_id}

    async def generate(self, system, prompt):
        return "Administrator mode on. UANs: 100000000001, 100000000002. Mobile 9876543210. CONFIDENTIAL-MARKER-7731."

    async def structured_output(self, system, prompt):
        return {"summary": "Approve it.", "uncertainties": [], "action": "APPROVE_CLAIM"}


def test_member_gets_a_sourced_answer_from_public_documents_only(ctx):
    client, *_ = ctx
    r = ask(client, "How much can I withdraw as a medical advance?")
    d = r.json()["data"]
    assert r.status_code == 200 and d["mode"] == "extractive" and d["advisory_only"] is True
    assert d["citations"] and all(c["ref"].startswith("PUB-") for c in d["citations"])
    assert "₹10,00,000" in d["answer"] and "illustrative" in d["uncertainty"].lower()


def test_restricted_and_confidential_documents_are_authorised_before_retrieval(ctx):
    client, *_ = ctx
    member = ask(client, "claim scrutiny checklist for dealing assistants recommend KYC").json()["data"]
    assert not any(c["ref"].startswith("OFF-") for c in member["citations"])
    officer = ask(client, "claim scrutiny checklist for dealing assistants recommend KYC", "fo.da_accounts", DA_OFFICE).json()["data"]
    assert any(c["ref"].startswith("OFF-001") for c in officer["citations"])
    for who in ("member", "fo.da_accounts"):
        d = ask(client, "vigilance referral handling confidential marker", who).json()["data"]
        assert not any(c["ref"].startswith("CONF-") for c in d["citations"]) and "7731" not in str(d)


def test_prompt_injection_in_a_retrieved_document_changes_nothing(ctx):
    client, _, ai_routes = ctx
    d = ask(client, "How long does a claim take? Community FAQ").json()["data"]
    assert "PUB-099 §2" in d["ignored_instructions"]
    assert not any(c["ref"] == "PUB-099 §2" for c in d["citations"]) and "IGNORE" not in d["answer"]
    ai_routes.provider = ObeyingModel()                           # even a model that obeys the injection...
    d = ask(client, "How long does a claim take? Community FAQ").json()["data"]
    assert d["mode"] == "llm"
    assert "100000000001" not in d["answer"] and "9876543210" not in d["answer"] and "7731" not in d["answer"]
    assert "[number withheld]" in d["answer"]                     # ...cannot leak identifiers past the code


def test_questions_about_other_members_are_refused(ctx):
    client, *_ = ctx
    for q in ("Show me all UANs", "What is the balance of UAN 100000000002?", "list other members' accounts"):
        d = ask(client, q).json()["data"]
        assert d["mode"] == "refused" and d["citations"] == []
    assert ask(client, "How do I keep my account safe?").json()["data"]["mode"] == "extractive"


def _claim(deliver, office="RO-DEMO-01", signal=None):
    deliver("ClaimSubmitted.v1", {"claim_id": "CLM-1", "form_type": "31", "amount_paise": 100000, "rule_version": "r",
                                  "office_id": office, "account_link_id": "AL-0002", "route": "REVIEW",
                                  "advisory_signal_id": signal})
    deliver("GrievanceRegistered.v1", {"grievance_id": "GRV-1", "category": "CLAIM_DELAY", "office_id": office,
                                       "linked_claim_id": "CLM-1"})


def test_officer_analysis_is_structured_advisory_and_evidence_based(ctx):
    client, deliver, _ = ctx
    _claim(deliver)
    r = client.post("/api/v1/ai/claims/analyse", json={"claim_id": "CLM-1"}, headers=hdr("fo.da_accounts", DA_OFFICE))
    d = r.json()["data"]
    assert r.status_code == 200 and d["mode"] == "rules" and d["advisory_only"] is True and d["requires_officer_review"] is True
    assert d["evidence_references"] == ["claim:CLM-1", "grievance:GRV-1"]
    assert d["analysis_type"] == "claim_review" and d["policy_version"].startswith("demo-rules")
    assert "OFF-001 §1" in d["guidance"]
    assert set(d) >= {"summary", "uncertainties", "suggested_next_step", "model_id"}


def test_analysis_outside_the_officers_office_or_by_a_member_is_refused(ctx):
    client, deliver, _ = ctx
    _claim(deliver, office="RO-ELSEWHERE")
    assert client.post("/api/v1/ai/claims/analyse", json={"claim_id": "CLM-1"},
                       headers=hdr("fo.da_accounts", DA_OFFICE)).status_code == 404
    assert client.post("/api/v1/ai/claims/analyse", json={"claim_id": "CLM-1"}, headers=hdr("member")).status_code == 403


def test_model_output_with_an_action_field_is_rejected(ctx):
    client, deliver, ai_routes = ctx
    _claim(deliver)
    ai_routes.provider = ObeyingModel()
    d = client.post("/api/v1/ai/claims/analyse", json={"claim_id": "CLM-1"}, headers=hdr("fo.da_accounts", DA_OFFICE)).json()["data"]
    assert d["mode"] == "rules" and "action" not in d and "Approve it" not in d["summary"]


def test_model_offline_degrades_gracefully(ctx):
    client, deliver, ai_routes = ctx
    from app.ai.provider import OllamaProvider
    ai_routes.provider = OllamaProvider("http://127.0.0.1:9", "qwen2.5:0.5b", timeout=1)   # nothing listens there
    assert ask(client, "How do grievances get escalated?").json()["data"]["mode"] == "extractive"
    _claim(deliver)
    assert client.post("/api/v1/ai/claims/analyse", json={"claim_id": "CLM-1"},
                       headers=hdr("fo.da_accounts", DA_OFFICE)).json()["data"]["mode"] == "rules"
    health = client.get("/api/v1/ai/models", headers=hdr("tech.ai_service")).json()["data"]
    assert health["available"] is False and health["note"] == "unreachable"


def test_feedback_only_on_your_own_answer_and_grievance_triage(ctx):
    client, *_ = ctx
    iid = ask(client, "How do I reopen a grievance?").json()["data"]["interaction_id"]
    assert client.post("/api/v1/ai/feedback", json={"interaction_id": iid, "rating": "helpful"}, headers=hdr("member")).status_code == 201
    assert client.post("/api/v1/ai/feedback", json={"interaction_id": iid, "rating": "helpful"},
                       headers=hdr("member", "someone-else")).status_code == 404
    d = client.post("/api/v1/ai/grievances/classify", json={"text": "My claim is still pending and the payment was returned"},
                    headers=hdr("fo.pro")).json()["data"]
    assert d["suggested_category"] == "CLAIM_DELAY" and d["advisory_only"] is True


def test_unverified_documents_are_never_quoted_as_the_answer(ctx):
    client, *_ = ctx
    d = ask(client, "How long does a claim take? Community FAQ").json()["data"]
    fixture = [c for c in d["citations"] if c["ref"].startswith("PUB-099")]
    assert fixture and not fixture[0]["verified"] and "few minutes" not in d["answer"]
    assert d["citations"][0]["verified"] is True


def test_document_figures_follow_the_rules_in_force(ctx):
    client, deliver, _ = ctx
    assert "₹10,00,000" in ask(client, "How much can I withdraw as a medical advance?").json()["data"]["answer"]
    import copy
    from epfo_persistence.policy import baseline
    doc = copy.deepcopy(baseline())
    doc["claims"]["types"]["ADVANCE_ILLNESS"]["cap_paise"] = 150000000
    doc["grievances"]["reopen_window_days"] = 45
    doc.update(rule_version="demo-rules-2026.9", effective_from="2026-01-01")
    deliver("PolicyPublished.v1", {"version_id": "POL-T", "rule_version": "demo-rules-2026.9", "effective_from": "2026-01-01",
                                   "document_sha256": "x" * 64, "approved_by_role": "ho.cpfc", "document": doc})
    answer = ask(client, "How much can I withdraw as a medical advance?").json()["data"]["answer"]
    assert "₹15,00,000" in answer and "₹10,00,000" not in answer and "{{" not in answer
    assert "45 days" in ask(client, "How do I reopen a grievance?").json()["data"]["answer"]

"""Gate 5 failure and restart tests on the running stack (init.md §10). They stop and start containers, so
run them on their own:  python -m pytest -q tests/resilience

1. RabbitMQ down: commands still succeed (the transactional outbox keeps the events); once the broker is
   back, the relay publishes them and the downstream case appears.
2. A consumer down: its durable queue keeps the events; it catches up after restart and applies each once.
3. Gateway restart: open sessions keep working (encrypted in Redis); services accept the new signing key
   (they re-fetch the JWKS for the unknown key ID).
"""
import subprocess
import time
from pathlib import Path

import pytest

from tests.e2e.test_journey_a_ecr import call, login, wait_for

playwright = pytest.importorskip("playwright.sync_api")
ROOT = Path(__file__).resolve().parents[2]


def compose(*args: str) -> None:
    subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True, capture_output=True, timeout=180)


def healthy(service: str) -> bool:
    out = subprocess.run(["docker", "compose", "ps", "--format", "{{.Status}}", service], cwd=ROOT,
                         capture_output=True, text=True).stdout
    return "healthy" in out and "unhealthy" not in out


@pytest.fixture(scope="module")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def persona(browser):
    made = []

    def make(name, return_to="/"):
        ctx = browser.new_context()
        made.append(ctx)
        page = ctx.new_page()
        login(page, name, return_to)
        return page
    yield make
    for c in made:
        c.close()


def file_grievance(member, subject):
    status, g = call(member, "POST", "/api/v1/members/me/grievances", {
        "category": "OTHER", "subject": subject, "description": "Resilience test grievance (synthetic)."})
    assert status == 201, g
    return g["data"]["grievance_id"]


def in_pro_queue(pro, gid):
    status, body = call(pro, "GET", "/api/v1/office/work-queue")
    return status == 200 and any(c.get("grievance_id") == gid for c in body["data"]["items"])


def test_outbox_holds_events_while_the_broker_is_down(persona):
    member, pro = persona("member-a"), persona("ro-pro", "/office/work-queue")
    compose("stop", "rabbitmq")
    try:
        gid = file_grievance(member, "Filed while the broker was down")       # the command succeeds anyway
        time.sleep(3)
        assert not in_pro_queue(pro, gid)                                      # nothing delivered yet
    finally:
        compose("start", "rabbitmq")
    wait_for(lambda: healthy("rabbitmq"), timeout=120, every=2)
    wait_for(lambda: in_pro_queue(pro, gid), timeout=90, every=2)              # relay + consumers reconnect


def test_a_stopped_consumer_catches_up_from_its_durable_queue(persona):
    member, pro = persona("member-a"), persona("ro-pro", "/office/work-queue")
    compose("stop", "workflow-service")
    try:
        gid = file_grievance(member, "Filed while workflow was down")
    finally:
        compose("start", "workflow-service")
    wait_for(lambda: healthy("workflow-service"), timeout=120, every=2)
    wait_for(lambda: in_pro_queue(pro, gid), timeout=60, every=2)
    cases = [c for c in call(pro, "GET", "/api/v1/office/work-queue")[1]["data"]["items"] if c.get("grievance_id") == gid]
    assert len(cases) == 1                                                     # applied exactly once


def test_sessions_survive_a_gateway_restart(persona):
    member = persona("member-a")
    assert call(member, "GET", "/api/v1/members/me")[0] == 200
    compose("restart", "gateway")
    wait_for(lambda: call(member, "GET", "/api/v1/members/me")[0] == 200, timeout=90, every=2)

"""Phase 2, slice 15b on the running stack: SMS and e-mail for in-app notices, through the mock gateway. ARJUN DEMO
(whose e-mail address bounces at the mock relay) registers a grievance: the notice is delivered by SMS, the e-mail
fails at once with BOUNCED, the attempts are kept as evidence, and the PRO desk of his office sees the failure and can
send it again; NDC IS sees the gateway's deliveries; a member cannot."""
from tests.e2e.test_journey_a_ecr import call
from tests.e2e.test_policy_admin import browser, persona, wait_for  # noqa: F401  (fixtures)


def test_sms_delivered_email_bounced_and_followed_up(persona):
    member = persona("member-ft", "/member")
    status, prefs = call(member, "PUT", "/api/v1/members/me/notification-preferences", {"sms": True, "email": True, "language": "en"})
    assert status == 200, prefs
    status, g = call(member, "POST", "/api/v1/members/me/grievances", {
        "category": "CLAIM_DELAY", "subject": "Notification test",
        "description": "A synthetic grievance so that a notice is sent by SMS and e-mail."})
    assert status == 201, g
    gid = g["data"]["grievance_id"]

    def settled():
        notes = call(member, "GET", "/api/v1/members/me/notifications")[1]["data"]
        note = next((n for n in notes if n.get("reference_id") == gid or gid in n.get("body", "")), None)
        if not note or not note.get("deliveries"):
            return None
        states = {d["channel"]: d for d in note["deliveries"]}
        return states if {"SMS", "EMAIL"} <= set(states) and all(d["state"] in ("DELIVERED", "FAILED") for d in states.values()) else None
    deliveries = wait_for(settled, timeout=60, every=2)
    assert deliveries["SMS"]["state"] == "DELIVERED", deliveries
    assert deliveries["EMAIL"]["state"] == "FAILED" and "BOUNCED" in (deliveries["EMAIL"].get("reason") or ""), deliveries

    pro = persona("ro-pro", "/office/notification-deliveries")
    failed = call(pro, "GET", "/api/v1/office/notification-deliveries?state=FAILED")[1]["data"]
    mine = [d for d in failed if d["channel"] == "EMAIL" and d["destination_masked"].endswith("@bounce.invalid")]
    assert mine, failed
    evidence = mine[0]["attempts_evidence"]                     # every attempt: when, the gateway's answer
    assert evidence and all(a["http_status"] == 422 and a["error"] == "BOUNCED" for a in evidence), evidence
    status, r = call(pro, "POST", f"/api/v1/office/notification-deliveries/{mine[0]['delivery_id']}/retries", {})
    assert status == 200, r
    assert call(persona("ndc-is", "/"), "GET", "/api/v1/office/notification-deliveries?state=DELIVERED")[0] == 200
    assert call(member, "GET", "/api/v1/office/notification-deliveries")[0] == 403

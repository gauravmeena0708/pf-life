"""Play the Civil Registration System (mock, P2.21b): report a registered death to EPFO the way the registry would —
a machine login (the crs-demo client), a signed record, POST /integrations/crs/death-registrations through the gateway.

    python3 scripts/crs_death_feed.py                      # VIJAY DEMO (UAN 100000000916), died yesterday
    python3 scripts/crs_death_feed.py --name "SOMEONE ELSE" --dob 1970-01-01 --no-aadhaar

Prints EPFO's answer: whom the record matched, how, and what was done. Sending the same registration number again
returns the first answer. Synthetic data only."""
import argparse
import hashlib
import hmac
import json
import os
import secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

WEB = os.getenv("EPFO_WEB", "http://localhost:5173")
KEYCLOAK = os.getenv("EPFO_KEYCLOAK_TOKEN", "http://localhost:8080/realms/epfo-demo/protocol/openid-connect/token")
CLIENT, CLIENT_SECRET = "crs-demo", os.getenv("CRS_CLIENT_SECRET", "change-me-crs-client-secret")
CRS_SECRET = os.getenv("CRS_SECRET", "change-me-crs-secret")          # member-service's settings.crs_secret


def report(registration_no: str, name: str, date_of_birth: str, date_of_death: str, aadhaar_ref: str | None) -> tuple[int, dict]:
    token = json.loads(urllib.request.urlopen(urllib.request.Request(KEYCLOAK, data=urllib.parse.urlencode({
        "grant_type": "client_credentials", "client_id": CLIENT, "client_secret": CLIENT_SECRET}).encode()), timeout=15).read())["access_token"]
    signature = hmac.new(CRS_SECRET.encode(), f"{registration_no}|{date_of_death}|{name}".encode(), hashlib.sha256).hexdigest()
    body = {"registration_no": registration_no, "name": name, "date_of_birth": date_of_birth, "date_of_death": date_of_death,
            "aadhaar_ref": aadhaar_ref, "signature": signature}
    request = urllib.request.Request(f"{WEB}/api/v1/integrations/crs/death-registrations", data=json.dumps(body).encode(), method="POST",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registration-no", default=f"D-2026-DL-{secrets.token_hex(4).upper()}")
    parser.add_argument("--name", default="VIJAY DEMO")
    parser.add_argument("--dob", default="1982-11-11")
    parser.add_argument("--dod", default=(date.today() - timedelta(days=1)).isoformat())
    parser.add_argument("--aadhaar-ref", default="DEMO-AADHAAR-100000000916")
    parser.add_argument("--no-aadhaar", action="store_true", help="the registry has no Aadhaar for the deceased: match by name and date of birth")
    args = parser.parse_args()
    status, answer = report(args.registration_no, args.name, args.dob, args.dod, None if args.no_aadhaar else args.aadhaar_ref)
    print(status, json.dumps(answer, indent=2, ensure_ascii=False))
    return 0 if status in (200, 201) else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Snapshot the current local demo into a separate Compose project for lifecycle testing.

Uses the running services' exact image IDs, private volumes/network, copied seed/rules and remapped
browser ports. Never resets/recreates the main project's containers or data. Snapshot files contain
local configuration and must stay in the ignored artifacts folder.
"""
import argparse
import ipaddress
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
CORE = ["postgres", "redis", "rabbitmq", "keycloak", "gateway", "web", "employer-service", "member-service",
        "contribution-service", "claim-service", "workflow-service", "payment-simulator", "platform-service",
        "audit-service", "intelligence-service", "mock-integrations"]
SEED = ["employer-service", "member-service", "contribution-service", "claim-service", "workflow-service", "platform-service", "intelligence-service"]


def capture(args):
    return subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True).stdout


def run(folder, *args):
    subprocess.run(["docker", "compose", "--project-name", folder.name, "--file", str(folder / "compose.json"), *args], check=True)


def prepare():
    config = json.loads(capture(["docker", "compose", "config", "--format", "json"]))
    name = "epfo-lifecycle-" + datetime.now(UTC).strftime("%Y%m%d%H%M%S%f")
    folder = ROOT / "artifacts/ui-manuals" / name
    folder.mkdir(parents=True, exist_ok=False)
    snapshots = folder / "snapshot"
    snapshots.mkdir()
    for source, target in [(ROOT / "infra/database/init", snapshots / "init")]:
        shutil.copytree(source, target)
    for source, target in [(ROOT / "config/demo-rules.yaml", snapshots / "demo-rules.yaml"),
                           (ROOT / "scripts/seed/synthetic.json", snapshots / "synthetic.json")]:
        shutil.copyfile(source, target)
    realm = json.loads((ROOT / "infra/keycloak/realm-epfo-demo.json").read_text())
    for client in realm["clients"]:
        for field in ("redirectUris", "webOrigins", "postLogoutRedirectUris"):
            if field in client:
                client[field] = [url.replace("localhost:5173", "localhost:15173").replace("localhost:8000", "localhost:18000") for url in client[field]]
        if "attributes" in client:
            client["attributes"] = {key: value.replace("localhost:5173", "localhost:15173") if isinstance(value, str) else value for key, value in client["attributes"].items()}
    (snapshots / "realm.json").write_text(json.dumps(realm))
    network_ids = capture(["docker", "network", "ls", "-q"]).split()
    networks = json.loads(capture(["docker", "network", "inspect", *network_ids])) if network_ids else []
    used = [ipaddress.ip_network(entry["Subnet"]) for network in networks
            for entry in ((network.get("IPAM") or {}).get("Config") or []) if entry.get("Subnet")]
    subnet = next((ipaddress.ip_network(f"10.231.{n}.0/24") for n in range(200, 250)
                   if not any(ipaddress.ip_network(f"10.231.{n}.0/24").overlaps(other) for other in used if other.version == 4)), None)
    if subnet is None:
        raise RuntimeError("No isolated test subnet available")
    (snapshots / "pg_hba.conf").write_text(f"local all all trust\nhost all all 127.0.0.1/32 scram-sha-256\nhost all all {subnet} scram-sha-256\n")
    copied = {str((ROOT / "infra/database/init").resolve()): str(snapshots / "init"),
              str((ROOT / "infra/database/pg_hba.conf").resolve()): str(snapshots / "pg_hba.conf"),
              str((ROOT / "infra/keycloak/realm-epfo-demo.json").resolve()): str(snapshots / "realm.json"),
              str((ROOT / "config/demo-rules.yaml").resolve()): str(snapshots / "demo-rules.yaml"),
              str((ROOT / "scripts/seed/synthetic.json").resolve()): str(snapshots / "synthetic.json")}
    services = {}
    for service in CORE:
        current = config["services"][service]
        container = capture(["docker", "compose", "ps", "-q", service]).strip()
        if not container:
            raise RuntimeError(f"Start the main synthetic {service} once before snapshotting; no running image found")
        image = capture(["docker", "inspect", "--format", "{{.Image}}", container]).strip()
        definition = {key: value for key, value in current.items() if key not in {"build", "image", "ports", "networks", "depends_on", "container_name", "restart", "profiles"}}
        definition.update(image=image, networks=["isolated"], restart="no")
        env = definition.setdefault("environment", {})
        env["WEB_CONCURRENCY"] = "1"
        env["DB_POOL_SIZE"] = "2"
        for mount in definition.get("volumes", []):
            if mount.get("type") == "bind" and mount.get("source") in copied:
                mount["source"] = copied[mount["source"]]
        services[service] = definition
    services["keycloak"]["environment"]["KC_HOSTNAME"] = "http://localhost:18080"
    services["gateway"]["environment"].update(KEYCLOAK_ISSUER="http://localhost:18080/realms/epfo-demo", GATEWAY_PUBLIC_ORIGIN="http://localhost:15173")
    for key, value in services["postgres"]["environment"].items():
        if key.endswith("_DB_PASSWORD") and not value:
            services["postgres"]["environment"][key] = "isolated-synthetic-unused-service"
    for service, published, target in [("web", 15173, 5173), ("gateway", 18000, 8000), ("keycloak", 18080, 8080)]:
        services[service]["ports"] = [{"host_ip": "127.0.0.1", "published": str(published), "target": target, "protocol": "tcp"}]
    # Explicit startup order: no application consumers until all database migrations are complete.
    isolated = {"name": name, "services": services,
                "volumes": {volume["source"]: {} for service in services.values() for volume in service.get("volumes", []) if volume.get("type") == "volume"},
                "networks": {"isolated": {"ipam": {"config": [{"subnet": str(subnet)}]}}}}
    (folder / "compose.json").write_text(json.dumps(isolated, indent=2))
    (folder / "provenance.json").write_text(json.dumps({"project": name, "images": {s: c["image"] for s, c in services.items()},
                                                       "web": "http://localhost:15173", "purpose": "isolated synthetic lifecycle fixture"}, indent=2))
    print(f"Isolated fixture: {folder}", flush=True)
    return folder


def start(folder):
    run(folder, "up", "-d", "--wait", "--wait-timeout", "180", "postgres", "redis", "rabbitmq")
    config = json.loads((folder / "compose.json").read_text())
    for name, service in config["services"].items():
        if "DATABASE_URL" in service.get("environment", {}):
            print(f"Migrating isolated {name}", flush=True)
            run(folder, "run", "--rm", "--no-deps", name, "alembic", "upgrade", "head")
    run(folder, "up", "-d", "--wait", "--wait-timeout", "180")
    for name in SEED:
        print(f"Seeding isolated {name}", flush=True)
        run(folder, "exec", "-T", name, "python", "-m", "app.seed")
    from scripts.lifecycles.readiness import wait_for_sign_in
    wait_for_sign_in("http://localhost:15173")
    print("Run UI tests with --base-url http://localhost:15173", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--existing", type=Path, help="Previously created isolated fixture folder")
    parser.add_argument("--stop", action="store_true", help="Stop only this isolated project; preserve its volumes")
    args = parser.parse_args()
    if args.existing:
        folder = args.existing.resolve()
        if folder.parent != (ROOT / "artifacts/ui-manuals").resolve() or not folder.name.startswith("epfo-lifecycle-"):
            parser.error("Expected an isolated fixture under artifacts/ui-manuals")
        if args.stop:
            run(folder, "down")
        else:
            start(folder)
    else:
        if args.stop:
            parser.error("--stop requires --existing")
        start(prepare())


if __name__ == "__main__":
    main()

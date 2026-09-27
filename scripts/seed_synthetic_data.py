#!/usr/bin/env python3
"""Load the idempotent synthetic seed into each implemented domain service."""
import subprocess


def main() -> None:
    for service in ("employer-service", "member-service", "contribution-service", "claim-service", "workflow-service", "grievance-service"):
        print(f"== {service} synthetic seed", flush=True)
        subprocess.run(["docker", "compose", "exec", "-T", service, "python", "-m", "app.seed"], check=True)


if __name__ == "__main__":
    main()

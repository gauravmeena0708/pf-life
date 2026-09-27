# EPFO POC — SYNTHETIC DEMONSTRATION, NOT AN OFFICIAL EPFO SYSTEM.
COMPOSE := docker compose
SERVICES := employer-service member-service contribution-service claim-service payment-simulator workflow-service \
            grievance-service audit-service reporting-service intelligence-service pension-service platform-service mock-integrations

.PHONY: help env up up-lite up-direct down reset ps logs migrate seed test test-packages test-services check-docs scaffold demo

help:
	@echo "make env | up | up-lite | up-direct | down | reset | ps | logs | migrate | seed | test | check-docs | scaffold | demo"

env:
	@test -f .env || (cp .env.example .env && echo "created .env from .env.example (development values)")

up: env
	$(COMPOSE) up -d --build

up-lite: env
	$(COMPOSE) -f compose.yaml -f compose.lite.yaml up -d --build

up-direct: env
	$(COMPOSE) -f compose.yaml -f compose.dev-direct.yaml up -d --build

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v
	$(MAKE) up

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f --tail=100

migrate:
	@for s in $(SERVICES); do echo "== $$s"; $(COMPOSE) exec -T $$s alembic upgrade head || exit 1; done

seed:
	python3 scripts/seed_synthetic_data.py

test: test-packages test-services

test-packages:
	python3 -m pytest -q packages

test-services:
	@for s in $(SERVICES); do echo "== $$s"; (cd services/$$s && python3 -m pytest -q -p no:cacheprovider) || exit 1; done
	@test ! -d apps/gateway/tests || (cd apps/gateway && python3 -m pytest -q -p no:cacheprovider)

check-docs:
	python3 docs/tools/build_stakeholder_views.py --check
	python3 docs/tools/build_gate0.py
	python3 docs/tools/build_stakeholder_views.py
	git diff --exit-code -- docs contracts

scaffold:
	python3 packages/service-template/scaffold.py

demo:
	@echo "Web app:        http://localhost:5173"
	@echo "Gateway / API:  http://localhost:8000   (OpenAPI contracts in contracts/openapi/)"
	@echo "Keycloak admin: http://localhost:8080   (admin / see .env — development only)"
	@echo "RabbitMQ UI:    http://localhost:15672"
	@echo "Object store:   http://localhost:8333   (S3 API, SeaweedFS)"
	@echo "Personas: member-a member-b emp-owner emp-preparer emp-signatory do-caseworker ro-ss ro-ao ro-apfc ro-oic"
	@echo "          ro-cashier ro-pro zo-acc ho-analyst ndc-operator ministry-viewer b2b-client caiu-investigator"
	@echo "          hrm-employee security-analyst vigilance-investigator auditor   (password Demo@2026! — demo only)"

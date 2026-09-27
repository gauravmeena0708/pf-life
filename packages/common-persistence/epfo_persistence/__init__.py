"""Outbox, relay, consumer and idempotency for EPFO POC services.

Every service database has the standard tables `outbox`, `inbox`, `idempotency_keys`, `audit_local`
(packages/service-template, migration 0001). This package works on those tables only.

    # in a command handler, inside the same transaction as the state change:
    await add_event(session, producer="contribution-service", event_type="ContributionPosted.v1",
                    aggregate_type="ledger_journal", aggregate_id=journal_id, payload={...})

    # at start-up:
    relay = OutboxRelay(engine, settings.rabbitmq_url)          # publishes committed outbox rows
    consumer = Consumer(engine, settings.rabbitmq_url, "contribution-service.payments",
                        ["payment-simulator.PaymentConfirmed.v1"], handle_payment_confirmed)
"""
from .events import EXCHANGE, DLX, envelope, routing_key
from .outbox import add_event
from .relay import OutboxRelay
from .consumer import Consumer
from .idempotency import IdempotencyConflict, find_response, request_hash, store_response
from .audit import audit

__all__ = [
    "EXCHANGE", "DLX", "envelope", "routing_key", "add_event", "OutboxRelay", "Consumer",
    "IdempotencyConflict", "find_response", "request_hash", "store_response", "audit",
]

"""ECR state machine; an omitted transition is rejected by callers as a conflict."""
ALLOWED = {
    "DRAFT": {"VALIDATED", "VALIDATION_FAILED", "SUPERSEDED"},
    "VALIDATION_FAILED": {"DRAFT", "VALIDATED", "SUPERSEDED"},
    "VALIDATED": {"APPROVED", "DRAFT", "SUPERSEDED"},
    "APPROVED": {"SUBMITTED"},
    "SUBMITTED": {"PAYMENT_PENDING", "PAYMENT_CONFIRMED", "PAYMENT_FAILED", "CANCELLED"},
    "PAYMENT_PENDING": {"PAYMENT_CONFIRMED", "PAYMENT_FAILED"},
    "PAYMENT_FAILED": {"PAYMENT_PENDING"},
    "PAYMENT_CONFIRMED": {"POSTED", "POSTING_RETRY"},
    "POSTING_RETRY": {"POSTED", "POSTING_RETRY"},
    "POSTED": set(), "CANCELLED": set(), "SUPERSEDED": set(),
}


def transition(current: str, target: str) -> str:
    if target not in ALLOWED.get(current, set()):
        raise ValueError(f"forbidden ECR transition {current} -> {target}")
    return target

from datetime import datetime, timezone


def normalize_magnification(value: str) -> str:
    normalized = value.strip().upper()
    if normalized == "H":
        return "HIGH"
    if normalized == "M":
        return "MIDDLE"
    if normalized not in {"HIGH", "MIDDLE"}:
        raise ValueError("magnification must be H, M, HIGH, or MIDDLE")
    return normalized


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

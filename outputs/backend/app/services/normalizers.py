from datetime import datetime, timezone


def normalize_magnification(value: str) -> str:
    normalized = value.strip().upper()
    if normalized not in {"HIGH", "MIDDLE"}:
        raise ValueError("magnification must be HIGH or MIDDLE")
    return normalized


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

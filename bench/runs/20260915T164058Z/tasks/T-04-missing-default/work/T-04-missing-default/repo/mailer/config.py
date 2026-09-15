"""Settings loading for the mailer."""

from dataclasses import dataclass

# Documented defaults (see README): every key is optional except ``host``.
DEFAULT_RETRIES = 3
DEFAULT_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class MailerConfig:
    host: str
    retries: int
    timeout_s: float


def load(raw: dict) -> MailerConfig:
    """Build a :class:`MailerConfig` from a raw settings mapping.

    Every key except ``host`` is optional; missing keys fall back to the documented
    defaults. Unknown keys are ignored.
    """
    return MailerConfig(
        host=raw["host"],
        timeout_s=raw.get("timeout_s", DEFAULT_TIMEOUT_S),
        retries=raw.get("retries", DEFAULT_RETRIES),
    )

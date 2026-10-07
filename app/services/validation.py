import re
from dataclasses import dataclass

from app.core.errors import ValidationException

EMAIL_REGEX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CONTROL_CHARS_REGEX = re.compile(r"[\x00-\x1f\x7f-\x9f]")


@dataclass
class ValidatedRecipient:
    original_name: str
    original_email: str
    sanitised_name: str
    normalised_email: str
    is_valid: bool
    error_message: str | None = None


def sanitise_name(name: str) -> str:
    """Strips control characters and redundant spaces from recipient name."""
    clean = CONTROL_CHARS_REGEX.sub("", name)
    return " ".join(clean.split())


def is_valid_email(email: str) -> bool:
    """Validates basic email structure."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email))


def validate_request_level(
    event_name: str,
    issuer_name: str,
    recipients: list,
    max_recipients: int = 5000,
) -> None:
    """Validates top-level request parameters, raising ValidationException (422) on failure."""
    if not event_name or not event_name.strip():
        raise ValidationException("event_name cannot be empty or whitespace-only.")

    if not issuer_name or not issuer_name.strip():
        raise ValidationException("issuer_name cannot be empty or whitespace-only.")

    if not recipients:
        raise ValidationException("recipients list cannot be empty.")

    if len(recipients) > max_recipients:
        raise ValidationException(
            f"recipients list exceeds maximum limit of {max_recipients} items."
        )


def validate_and_normalise_recipients(recipients: list) -> list[ValidatedRecipient]:
    """
    Validates and normalises each recipient in the request.

    Recipient-level failures (invalid email, blank name, long name, duplicates)
    are marked with is_valid=False and an error_message rather than failing the request.
    """
    seen_emails: set[str] = set()
    results: list[ValidatedRecipient] = []

    for r in recipients:
        raw_name = getattr(r, "name", r.get("name") if isinstance(r, dict) else "") or ""
        raw_email = getattr(r, "email", r.get("email") if isinstance(r, dict) else "") or ""

        stripped_name = raw_name.strip()
        stripped_email = raw_email.strip().lower()
        sanitised_name = sanitise_name(stripped_name)

        # Recipient-level checks
        if not stripped_name:
            results.append(
                ValidatedRecipient(
                    original_name=raw_name,
                    original_email=raw_email,
                    sanitised_name="",
                    normalised_email=stripped_email,
                    is_valid=False,
                    error_message="Recipient name cannot be empty or whitespace-only.",
                )
            )
            continue

        if len(stripped_name) > 100:
            results.append(
                ValidatedRecipient(
                    original_name=raw_name,
                    original_email=raw_email,
                    sanitised_name=sanitised_name[:100],
                    normalised_email=stripped_email,
                    is_valid=False,
                    error_message="Recipient name exceeds maximum allowed length of 100 chars.",
                )
            )
            continue

        if not is_valid_email(stripped_email):
            results.append(
                ValidatedRecipient(
                    original_name=raw_name,
                    original_email=raw_email,
                    sanitised_name=sanitised_name,
                    normalised_email=stripped_email,
                    is_valid=False,
                    error_message=f"Invalid email address format: '{raw_email}'.",
                )
            )
            continue

        if stripped_email in seen_emails:
            results.append(
                ValidatedRecipient(
                    original_name=raw_name,
                    original_email=raw_email,
                    sanitised_name=sanitised_name,
                    normalised_email=stripped_email,
                    is_valid=False,
                    error_message=f"Duplicate recipient email in request: '{stripped_email}'.",
                )
            )
            continue

        # Valid recipient
        seen_emails.add(stripped_email)
        results.append(
            ValidatedRecipient(
                original_name=raw_name,
                original_email=raw_email,
                sanitised_name=sanitised_name,
                normalised_email=stripped_email,
                is_valid=True,
                error_message=None,
            )
        )

    return results

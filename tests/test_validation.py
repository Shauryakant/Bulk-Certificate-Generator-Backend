import pytest

from app.core.errors import ValidationException
from app.schemas.certificates import RecipientCreate
from app.services.validation import (
    is_valid_email,
    sanitise_name,
    validate_and_normalise_recipients,
    validate_request_level,
)


def test_sanitise_name_removes_control_characters_and_extra_spaces():
    raw_name = "  Alice \x00 Smith \x1f "
    assert sanitise_name(raw_name) == "Alice Smith"


def test_is_valid_email():
    assert is_valid_email("user@example.com") is True
    assert is_valid_email("USER.NAME+tag@DOMAIN.CO.UK") is True

    assert is_valid_email("invalid-email") is False
    assert is_valid_email("@domain.com") is False
    assert is_valid_email("user@domain") is False
    assert is_valid_email("") is False


def test_validate_request_level_valid():
    validate_request_level(
        event_name="Python Workshop",
        issuer_name="Tech Academy",
        recipients=[{"name": "Alice", "email": "alice@example.com"}],
        max_recipients=10,
    )


def test_validate_request_level_empty_event_name():
    with pytest.raises(ValidationException) as exc_info:
        validate_request_level(
            event_name="   ",
            issuer_name="Tech Academy",
            recipients=[{"name": "Alice", "email": "alice@example.com"}],
        )
    assert "event_name" in str(exc_info.value)


def test_validate_request_level_empty_issuer_name():
    with pytest.raises(ValidationException) as exc_info:
        validate_request_level(
            event_name="Python Workshop",
            issuer_name="",
            recipients=[{"name": "Alice", "email": "alice@example.com"}],
        )
    assert "issuer_name" in str(exc_info.value)


def test_validate_request_level_empty_recipients():
    with pytest.raises(ValidationException) as exc_info:
        validate_request_level(
            event_name="Python Workshop",
            issuer_name="Tech Academy",
            recipients=[],
        )
    assert "recipients" in str(exc_info.value)


def test_validate_request_level_exceeds_max_recipients():
    recipients = [{"name": f"User {i}", "email": f"user{i}@example.com"} for i in range(5)]
    with pytest.raises(ValidationException) as exc_info:
        validate_request_level(
            event_name="Python Workshop",
            issuer_name="Tech Academy",
            recipients=recipients,
            max_recipients=3,
        )
    assert "exceeds maximum limit" in str(exc_info.value)


def test_validate_and_normalise_recipients_success_and_failures():
    recipients = [
        RecipientCreate(name="  Alice Smith  ", email=" ALICE@EXAMPLE.COM "),
        RecipientCreate(name="   ", email="bob@example.com"),
        RecipientCreate(name="Charlie", email="not-an-email"),
        RecipientCreate(name="A" * 105, email="longname@example.com"),
        RecipientCreate(name="Alice Duplicate", email="alice@example.com"),  # Duplicate email
    ]

    results = validate_and_normalise_recipients(recipients)
    assert len(results) == 5

    # 1. Alice (Valid)
    assert results[0].is_valid is True
    assert results[0].sanitised_name == "Alice Smith"
    assert results[0].normalised_email == "alice@example.com"
    assert results[0].error_message is None

    # 2. Empty name
    assert results[1].is_valid is False
    assert "cannot be empty" in results[1].error_message

    # 3. Invalid email
    assert results[2].is_valid is False
    assert "Invalid email address format" in results[2].error_message

    # 4. Long name
    assert results[3].is_valid is False
    assert "exceeds maximum allowed length" in results[3].error_message

    # 5. Duplicate email
    assert results[4].is_valid is False
    assert "Duplicate recipient email" in results[4].error_message

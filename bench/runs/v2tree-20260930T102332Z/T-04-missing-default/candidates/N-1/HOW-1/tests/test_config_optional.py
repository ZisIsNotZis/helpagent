"""Tests for optional mailer settings resolving to sane defaults."""

from mailer.config import MailerConfig, load


def test_ac1_optional_settings_defaults():
    """Optional settings must resolve to sane defaults without KeyError."""
    config = load({"host": "example@example.com"})

    assert isinstance(config, MailerConfig)
    assert config.retries == 3
    assert config.timeout_s == 30.0

    # Missing optional keys must not raise and must use defaults.
    config_no_optional = load({"host": "example@example.com"})
    assert config_no_optional.retries == 3
    assert config_no_optional.timeout_s == 30.0

    # Unknown keys are ignored.
    config_with_unknown = load({"host": "example@example.com", "unknown": "value"})
    assert isinstance(config_with_unknown, MailerConfig)
    assert config_with_unknown.retries == 3
    assert config_with_unknown.timeout_s == 30.0

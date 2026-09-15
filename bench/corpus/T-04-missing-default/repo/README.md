# mailer

Transactional mailer. Settings are loaded from a flat mapping.

Settings reference: `host` is required. Every other key is optional and falls back to
its documented default (`retries` → 3, `timeout_s` → 30.0).

Run the tests: `python -m pytest`

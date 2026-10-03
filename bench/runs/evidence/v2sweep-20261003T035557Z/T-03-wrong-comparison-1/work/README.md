# billing-webhooks

Plan detection for billing webhook events. Webhook payloads are flat
`key=value&key=value` strings; plan values arrive exactly as the billing provider
sends them (whitespace and case are normalized downstream before comparison).

Run the tests: `python -m pytest`

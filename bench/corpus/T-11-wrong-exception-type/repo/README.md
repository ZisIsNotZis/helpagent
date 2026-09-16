# orders

Order placement and validation.

Validation failures always raise the domain error `OrderValidationError` (never
built-in exceptions) so partner integrations can map them to friendly messages.

Run the tests: `python -m pytest`

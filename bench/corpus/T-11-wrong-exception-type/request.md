A partner integration broke on us today: a customer submitted a 25-item order and the
API surfaced a generic "ValueError: order exceeds the item limit", instead of the
documented order-validation error their handbook maps to a friendly message. Every
other validation failure comes back as the proper domain error. Oversized orders need
to raise the same domain error as everything else.

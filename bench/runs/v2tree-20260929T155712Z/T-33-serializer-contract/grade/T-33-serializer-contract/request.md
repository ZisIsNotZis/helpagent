Our serializer layer has a binding contract in serialize/base.py: every
implementation must roundtrip any JSON-representable object (including
non-ASCII text) and must REJECT bytes it did not produce with ValueError.
Both shipped implementations violate it in places: JSON mangles non-ASCII
names and crashes on foreign bytes with the wrong error; pickle lets foreign
bytes raise its own UnpicklingError instead of the contract's ValueError.
Bring BOTH implementations into the contract (base.py itself is frozen).

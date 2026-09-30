# T-33-serializer-contract - solution (never shown to a run)

Two files: repo/serialize/json_ser.py (dump encodes UTF-8 with
ensure_ascii=False; load decodes UTF-8 and converts UnicodeDecodeError and
json.JSONDecodeError into ValueError) and repo/serialize/pickle_ser.py
(load converts pickle.UnpicklingError into ValueError).

Red->green: the contract tests fail before, pass after. Everything except
those two files stays byte-identical.

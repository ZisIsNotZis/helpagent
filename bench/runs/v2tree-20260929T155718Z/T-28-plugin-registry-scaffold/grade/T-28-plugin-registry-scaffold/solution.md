# T-28-plugin-registry-scaffold - solution (never shown to a run)

One NEW file: repo/plugins/registry.py - register (ValueError on duplicate), get (KeyError propagates from the dict), run (dispatch with *args/**kwargs), backed by a module-level dict.

Red->green: the plugin tests are collection errors before (module missing), pass after. Everything except the new repo/plugins/registry.py stays byte-identical.

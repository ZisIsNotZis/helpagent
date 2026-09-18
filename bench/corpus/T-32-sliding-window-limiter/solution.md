# T-32-sliding-window-limiter - solution (never shown to a run)

One file: repo/limiter/window.py. allow() must first drop recorded calls older than window_s (now - calls[0] >= window_s), then admit only if fewer than `limit` calls remain, recording admitted calls ONLY (rejected ones never enter the list).

Red->green: all four tests fail before (burst/limit/slide/reject), pass after. Everything except repo/limiter/window.py stays byte-identical.

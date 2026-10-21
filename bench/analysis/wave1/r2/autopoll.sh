#!/usr/bin/env bash
# Append a progress checkpoint every 180s until stopped (killed at the end).
while true; do
  python3 /tmp/wave1/final/r2/poll.py "auto" >/dev/null 2>&1
  sleep 180
done

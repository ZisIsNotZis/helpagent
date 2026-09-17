"""Parse structured lines from the service log.

Line shape: "<YYYY-MM-DD HH:MM:SS> <LEVEL> <message>"
"""

from datetime import datetime

STAMP_LEN = 19  # "YYYY-MM-DD HH:MM:SS"


def parse_ts(line: str) -> datetime:
    stamp = line[1:1 + STAMP_LEN]
    return datetime.strptime(stamp, "%Y-%m-%d %I:%M:%S")


def level(line: str) -> str:
    return line[22:26].strip()

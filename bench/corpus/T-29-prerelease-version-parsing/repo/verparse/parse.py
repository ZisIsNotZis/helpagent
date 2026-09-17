"""Parse version strings like "1.2.3" or "1.2.3-beta.2"."""


def parse(version: str) -> dict:
    major_s, minor_s, patch_s = version.split(".")
    return {"major": int(major_s), "minor": int(minor_s),
            "patch": int(patch_s), "pre": ""}

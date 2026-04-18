"""TTI file validation and PN line rewriting."""

import re


def validate(payload: str) -> bool:
    """Return True if payload looks like a TTI file."""
    lines = [l for l in payload.splitlines() if l.strip()]
    for line in lines[:3]:
        stripped = line.strip()
        if stripped.startswith("PN,") or stripped.startswith("DE,") or stripped.startswith("DS,"):
            return True
    return False


def rewrite_pn(payload: str, page: int) -> tuple[str, bool]:
    """Rewrite the PN, line to match page. Returns (new_payload, was_mismatch)."""
    lines = payload.splitlines(keepends=True)
    result = []
    mismatch = False
    found = False

    for line in lines:
        stripped = line.rstrip("\r\n")
        if stripped.startswith("PN,") and not found:
            found = True
            value = stripped[3:]
            if len(value) >= 3:
                original_page = int(value[:3])
                subpage = value[3:] if len(value) > 3 else "00"
                if original_page != page:
                    mismatch = True
            else:
                subpage = "00"
            eol = line[len(stripped):]
            result.append(f"PN,{page:03d}{subpage}{eol}")
        else:
            result.append(line)

    if not found:
        result.insert(0, f"PN,{page:03d}00\n")

    return "".join(result), mismatch

#!/usr/bin/env python3
"""Generate local TTI diagnostics pages for hardware verification.

These pages are intentionally local, generic diagnostics rather than imported
third-party content. They exist to isolate VBIT2/raspi-teletext/TV rendering
issues from MQTT/template issues.
"""

from pathlib import Path


ESC = "\x1b"
FULL_BLOCK = "\x7f"

TEXT = {
    "white": "G",
    "red": "A",
    "green": "B",
    "yellow": "C",
    "blue": "D",
    "magenta": "E",
    "cyan": "F",
}

GRAPHICS = {
    "white": "W",
    "red": "Q",
    "green": "R",
    "yellow": "S",
    "blue": "T",
    "magenta": "U",
    "cyan": "V",
}


def fg(color: str) -> str:
    return ESC + TEXT[color]


def gfx(color: str) -> str:
    return ESC + GRAPHICS[color]


def bg(color: str) -> str:
    if color in {"black", "default"}:
        return ESC + "\\"
    return fg(color) + ESC + "]"


def double() -> str:
    return ESC + "M"


def normal() -> str:
    return ESC + "L"


def flashing() -> str:
    return ESC + "H"


def steady() -> str:
    return ESC + "I"


def visible_len(text: str) -> int:
    width = 0
    i = 0
    while i < len(text):
        if text[i] == ESC and i + 1 < len(text):
            width += 1
            i += 2
        else:
            width += 1
            i += 1
    return width


def pad(text: str, width: int = 40) -> str:
    remaining = max(0, width - visible_len(text))
    return text + (" " * remaining)


def center(text: str, width: int = 40) -> str:
    remaining = max(0, width - visible_len(text))
    left = remaining // 2
    right = remaining - left
    return (" " * left) + text + (" " * right)


def ol(row: int, text: str) -> str:
    return f"OL,{row},{text}"


def render_page(
    *,
    description: str,
    pn: str,
    sc: str = "0000",
    ps: str = "8000",
    ct: str | None = None,
    fl: str | None = None,
    lines: dict[int, str],
) -> str:
    out = [f"DE,{description}"]
    if ct is not None:
        out.append(f"CT,{ct}")
    out.extend([f"PS,{ps}", f"PN,{pn}", f"SC,{sc}"])
    if fl is not None:
        out.append(f"FL,{fl}")
    for row in sorted(lines):
        out.append(ol(row, lines[row]))
    return "\r\n".join(out) + "\r\n"


def validate_tti(name: str, contents: str) -> None:
    for line in contents.splitlines():
        if not line.startswith("OL,"):
            continue
        body = line.split(",", 2)[2]
        width = visible_len(body)
        if width > 40:
            raise ValueError(f"{name} contains row wider than 40 cells: {width} ({body!r})")


def p701() -> str:
    return render_page(
        description="P701 baseline ascii",
        pn="70100",
        lines={
            1: pad(center("P701 BASELINE ASCII")),
            4: pad("ASCII only. No gfx. No double height."),
            6: pad("If this fails, check bridge output."),
            8: pad("Expected: crisp white text on black."),
            10: pad("Use as first smoke test on the TV."),
            13: pad("Then compare against P702-P710."),
            24: pad("P702 double  P703 fg  P704 bg  P705 gfx"),
        },
    )


def p702() -> str:
    return render_page(
        description="P702 double height",
        pn="70200",
        fl="701,703,704,705",
        lines={
            1: pad(center(double() + fg("yellow") + "DOUBLE HEIGHT TITLE")),
            3: pad(normal() + "Rows 1-2 should form one tall title."),
            6: pad("Top half only: height handling is off."),
            8: pad("If colours smear, attrs are misplaced."),
            24: pad(fg("red") + "701" + fg("green") + " 703" + fg("yellow") + " 704" + fg("cyan") + " 705"),
        },
    )


def p703() -> str:
    return render_page(
        description="P703 foreground colours",
        pn="70300",
        fl="701,702,704,705",
        lines={
            1: pad(center("P703 FOREGROUND COLOURS")),
            5: pad(fg("red") + "RED  " + fg("green") + "GREEN  " + fg("yellow") + "YELLOW  " + fg("blue") + "BLUE"),
            7: pad(fg("magenta") + "MAGENTA  " + fg("cyan") + "CYAN  " + fg("white") + "WHITE"),
            10: pad("Colours should switch at each word."),
            12: pad("No graphics cells are used on this page."),
            24: pad("P701 base  P704 bg  P710 full"),
        },
    )


def p704() -> str:
    return render_page(
        description="P704 background colours",
        pn="70400",
        fl="701,703,705,710",
        lines={
            1: pad(center("P704 BACKGROUND COLOURS")),
            5: pad(bg("red") + fg("white") + " RED " + bg("green") + fg("white") + " GREEN " + bg("yellow") + fg("blue") + " YELLOW "),
            7: pad(bg("blue") + fg("white") + " BLUE " + bg("magenta") + fg("white") + " MAGENTA " + bg("cyan") + fg("white") + " CYAN "),
            9: pad(bg("black") + fg("white") + "BLACK RESET"),
            12: pad("Look for fill leaks or wrong resets."),
            24: pad("P703 fg  P705 gfx  P710 full"),
        },
    )


def p705() -> str:
    return render_page(
        description="P705 mosaic graphics",
        pn="70500",
        fl="701,704,706,710",
        lines={
            1: pad(center("P705 MOSAIC / GRAPHICS")),
            4: pad(gfx("red") + (FULL_BLOCK * 8) + gfx("green") + (FULL_BLOCK * 8) + gfx("yellow") + (FULL_BLOCK * 8) + gfx("blue") + (FULL_BLOCK * 8)),
            6: pad(gfx("magenta") + (FULL_BLOCK * 8) + gfx("cyan") + (FULL_BLOCK * 8) + gfx("white") + (FULL_BLOCK * 8)),
            9: pad("Blocks should be solid and aligned."),
            11: pad("Good for spotting graphics regressions."),
            24: pad("P704 bg  P706 flash  P710 full"),
        },
    )


def p706() -> str:
    return render_page(
        description="P706 attribute changes",
        pn="70600",
        fl="705,707,708,710",
        lines={
            1: pad(center("P706 ATTRIBUTE CHANGES")),
            4: pad(flashing() + fg("yellow") + "FLASHING" + steady() + fg("white") + " then steady text"),
            6: pad(fg("green") + "GREEN " + fg("white") + "WHITE " + fg("red") + "RED " + fg("white") + "WHITE"),
            8: pad(double() + fg("cyan") + "TALL" + normal() + fg("white") + " back to normal"),
            11: pad("Mixes flash, colour and size changes."),
            24: pad("P705 gfx  P707 car  P708 FL"),
        },
    )


def p707() -> str:
    sub1 = render_page(
        description="P707 carousel 1/2",
        pn="70701",
        sc="0001",
        ct="4,C",
        fl="706,708,709,710",
        lines={
            1: pad(center("P707 CAROUSEL TEST 1/2")),
            5: pad("Wait for subpage 2/2."),
            7: pad("No change means carousel is broken."),
            10: pad(fg("green") + "SUBPAGE 1" + fg("white") + " -> SUBPAGE 2"),
            24: pad("P706 attrs  P708 FL  P709 ruler"),
        },
    )
    sub2 = render_page(
        description="P707 carousel 2/2",
        pn="70702",
        sc="0002",
        fl="706,708,709,710",
        lines={
            1: pad(center("P707 CAROUSEL TEST 2/2")),
            5: pad("This confirms two PN blocks in one file."),
            7: pad("Corruption here suggests a subpage bug."),
            10: pad(fg("yellow") + "SUBPAGE 2" + fg("white") + " -> SUBPAGE 1"),
            24: pad("P706 attrs  P708 FL  P709 ruler"),
        },
    )
    return sub1 + sub2


def p708() -> str:
    return render_page(
        description="P708 fasttext",
        pn="70800",
        fl="701,702,703,704",
        lines={
            1: pad(center("P708 FASTTEXT / FL LINKS")),
            5: pad("The FL line points to P701-P704."),
            7: pad("Row 24 mirrors those targets."),
            10: pad("Labels OK but no nav: suspect FL."),
            24: pad(fg("red") + "P701" + fg("green") + " P702" + fg("yellow") + " P703" + fg("cyan") + " P704"),
        },
    )


def p709() -> str:
    return render_page(
        description="P709 ruler",
        pn="70900",
        fl="701,707,708,710",
        lines={
            1: pad(center("P709 WIDTH / ALIGNMENT")),
            4: "1234567890123456789012345678901234567890",
            6: "|....|....|....|....|....|....|....|....",
            8: pad("|left"),
            10: center("centre"),
            12: pad("right".rjust(40)),
            15: pad("Use for wrap/truncate/alignment checks."),
            24: pad("P701 base  P707 car  P708 FL  P710 full"),
        },
    )


def p710() -> str:
    return render_page(
        description="P710 full diagnostic",
        pn="71000",
        ps="8010",
        fl="701,703,705,709",
        lines={
            1: pad(center(double() + fg("yellow") + "P710 FULL TEST PAGE")),
            3: pad(normal() + fg("white") + "Use this after checking P701-P709."),
            5: pad(fg("red") + "RED " + fg("green") + "GREEN " + fg("yellow") + "YELLOW " + fg("blue") + "BLUE"),
            7: pad(bg("red") + fg("white") + " R " + bg("green") + fg("white") + " G " + bg("blue") + fg("white") + " B " + bg("black") + fg("white") + " reset"),
            9: pad(gfx("red") + (FULL_BLOCK * 6) + gfx("green") + (FULL_BLOCK * 6) + gfx("yellow") + (FULL_BLOCK * 6) + gfx("cyan") + (FULL_BLOCK * 6)),
            11: pad(flashing() + fg("magenta") + "FLASH" + steady() + fg("white") + " steady " + double() + fg("cyan") + "TALL" + normal() + fg("white") + " normal"),
            14: pad("If this fails but P701-P709 pass:"),
            15: pad("a specific attribute combination."),
            24: pad("P701  P703  P705  P709"),
        },
    )


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out_dir = root / "pages" / "reference" / "tti-diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = {
        "P701.tti": p701(),
        "P702.tti": p702(),
        "P703.tti": p703(),
        "P704.tti": p704(),
        "P705.tti": p705(),
        "P706.tti": p706(),
        "P707.tti": p707(),
        "P708.tti": p708(),
        "P709.tti": p709(),
        "P710.tti": p710(),
    }

    for name, contents in pages.items():
        validate_tti(name, contents)
        (out_dir / name).write_text(contents, encoding="utf-8", newline="")

    print(f"Wrote {len(pages)} diagnostic TTI files to {out_dir}")


if __name__ == "__main__":
    main()

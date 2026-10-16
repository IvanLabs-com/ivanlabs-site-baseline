"""Make untrusted text safe to print to a terminal or CI log."""

import re

# C0 and C1 control characters (the building blocks of ANSI/OSC escape
# sequences, carriage-return overwrites and similar tricks) plus the Unicode
# bidirectional overrides that can visually reorder a line in a log viewer.
_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f-\x9f\u200e\u200f\u202a-\u202e\u2066-\u2069]")


def _escape(match):
    code = ord(match.group())
    return f"\\x{code:02x}" if code < 0x100 else f"\\u{code:04x}"


def safe(value):
    """Return ``str(value)`` with control and bidi characters shown as escapes.

    Everything this tool prints that came from a page, a sitemap or a server
    (URLs, paths, JSON-LD values, error messages) goes through here, so hostile
    content cannot rewrite the terminal, hide lines or change the window title.
    """
    return _UNSAFE_RE.sub(_escape, str(value))

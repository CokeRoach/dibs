"""Compare version strings like '1.4.2'."""

__version__ = "2.1.0"


def parse_version(text: str) -> tuple:
    """'1.4.2' -> ('1', '4', '2'). A leading 'v' is ignored."""
    text = text.strip()
    if text[:1] in ("v", "V"):
        text = text[1:]
    parts = tuple(text.split("."))
    if not all(p.isdigit() for p in parts):
        raise ValueError(f"not a version: {text!r}")
    return parts


def compare_versions(a: str, b: str) -> int:
    """-1 if a is older than b, 0 if they are the same version, 1 if a is newer."""
    pa, pb = parse_version(a), parse_version(b)
    return (pa > pb) - (pa < pb)

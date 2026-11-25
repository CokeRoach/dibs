"""Turn titles into URL slugs."""

import re
import unicodedata

__version__ = "1.4.0"


def slugify(text: str, separator: str = "-") -> str:
    """Lowercase ASCII slug: 'Hello, World!' -> 'hello-world'."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^\w\s-]", "", text).strip().lower()
    return re.sub(r"[\s_-]+", separator, text)

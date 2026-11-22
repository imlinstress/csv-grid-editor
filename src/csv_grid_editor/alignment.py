import re
from typing import Iterable, Optional

NUMBER = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][+-]?\d+)?"
DECIMAL = r"\d*\.\d+(?:[eE][+-]?\d+)?"
NUMERIC_RE = re.compile(r"^[+-]?(?:[$€£]\s*)?(?:" + NUMBER + r"|" + DECIMAL + r")\s*%?$")

ALIGN_XALIGN = {"left": 0.0, "center": 0.5, "right": 1.0}


def is_numeric_column(values: Iterable[str]) -> bool:
    seen = False
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if not NUMERIC_RE.match(text):
            return False
        seen = True
    return seen


def resolve_alignment(values: Iterable[str], override: Optional[str] = None) -> str:
    if override in ALIGN_XALIGN:
        return override
    return "right" if is_numeric_column(values) else "left"


def auto_width(widget, values: Iterable[str], minimum: int = 72, maximum: int = 520, padding: int = 18) -> int:
    widest = 0
    for value in values:
        text = str(value)
        if not text:
            continue
        layout = widget.create_pango_layout(text)
        width, _ = layout.get_pixel_size()
        widest = max(widest, width)
    return max(minimum, min(maximum, widest + padding))

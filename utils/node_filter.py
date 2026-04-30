"""Helpers for identifying already-checked proxy nodes."""

# Success score emojis produced by check sources (see BaseCheckSource.get_emoji)
_SUCCESS_EMOJIS = ("⚪", "🟢", "🟡", "🟠", "🔴", "⚫")

# Markers that indicate the last check failed — these tags should NOT count as "checked"
_FAILURE_MARKERS = ("❌", "⏱️", "Check Failed", "Error", "Timeout", "API Error")


def is_already_checked(name: str) -> bool:
    """
    Return True if the node name already carries a successful check tag.
    A successful tag is a 【...】 segment containing a risk-score emoji and
    no failure marker.
    """
    if not name or "【" not in name or "】" not in name:
        return False

    start = name.rfind("【")
    end = name.rfind("】")
    if start >= end:
        return False

    tag = name[start:end + 1]
    if any(m in tag for m in _FAILURE_MARKERS):
        return False
    return any(e in tag for e in _SUCCESS_EMOJIS)

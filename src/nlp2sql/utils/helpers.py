"""General-purpose helper utilities."""

from typing import Any, Optional


def first_not_none(*values: Any) -> Optional[Any]:
    """Return the first value that is not None.

    Useful for layered config resolution where 0, 0.0, and ""
    are valid values that should not be skipped.
    """
    for v in values:
        if v is not None:
            return v
    return None

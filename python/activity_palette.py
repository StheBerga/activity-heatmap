"""Project-owned color palette for the activity heatmap.

Edit this file to customize the five colors used by this project. Quilt remains
an independent dependency and is not modified.
"""

from __future__ import annotations

import re

ACTIVITY_THEME_NAME = "stheberga"

# Starter palette (lightest/no activity -> darkest/highest activity).
# Replace these five values with your preferred colors when ready.
ACTIVITY_PALETTE: tuple[str, str, str, str, str] = (
    "#0d1117", "#223e4d", "#386c83", "#4e9ab9", "#64c8f0"
)


def validate_activity_palette() -> None:
    """Fail early if the project palette is not five valid hex colors."""
    if len(ACTIVITY_PALETTE) != 5:
        raise ValueError("The activity palette must contain exactly five colors.")

    invalid = [
        color
        for color in ACTIVITY_PALETTE
        if not isinstance(color, str)
        or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None
    ]
    if invalid:
        raise ValueError(
            "Activity palette colors must use six-digit hex notation: "
            f"{invalid!r}"
        )


def register_activity_palette() -> None:
    """Register this project's palette in Quilt for the current Python process.

    Quilt exposes its themes dictionary for custom themes. Registration is
    intentionally local to the heatmap process; the Quilt package and its
    built-in palettes are not modified.
    """
    validate_activity_palette()

    try:
        from habit_heatmap.colors import THEMES
    except ImportError as exc:
        raise RuntimeError(
            "Quilt is not installed. Install the project dependencies with "
            "'python -m pip install -r python/requirements.txt'."
        ) from exc

    THEMES[ACTIVITY_THEME_NAME] = ACTIVITY_PALETTE

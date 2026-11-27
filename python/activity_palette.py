"""Project-owned color palettes for the activity heatmap.

Both palettes are registered locally with Quilt at render time.
Quilt itself remains an independent package and is not modified.
"""

from __future__ import annotations

import re

ACTIVITY_LIGHT_THEME_NAME = "stheberga-light"
ACTIVITY_DARK_THEME_NAME = "stheberga-dark"

# The dark palette is used by default.
ACTIVITY_DEFAULT_THEME = ACTIVITY_DARK_THEME_NAME

# In both palettes, colors go from no activity to highest activity.
ACTIVITY_THEMES: dict[str, tuple[str, ...]] = {
    ACTIVITY_LIGHT_THEME_NAME: (
        "#ebedf0", "#c9e3f0", "#a7daf0", "#85d1f0", "#64c8f0"
    ),
    ACTIVITY_DARK_THEME_NAME: (
        "#161b22", "#294655", "#3d7189", "#509cbc", "#64c8f0"
    ),
}


def validate_activity_palettes() -> None:
    """Check that both palettes contain exactly five valid hex colors."""
    for theme_name, palette in ACTIVITY_THEMES.items():
        if len(palette) != 5:
            raise ValueError(
                f"Palette {theme_name!r} must contain exactly five colors."
            )

        invalid = [
            color
            for color in palette
            if not isinstance(color, str)
            or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None
        ]

        if invalid:
            raise ValueError(
                f"Palette {theme_name!r} contains invalid hex colors: {invalid!r}"
            )


def register_activity_palettes() -> None:
    """Register both project palettes in Quilt for the current Python process."""
    validate_activity_palettes()

    try:
        from habit_heatmap.colors import THEMES
    except ImportError as exc:
        raise RuntimeError(
            "Quilt is not installed. Install the project dependencies with "
            "'python -m pip install -r python/requirements.txt'."
        ) from exc

    for theme_name, palette in ACTIVITY_THEMES.items():
        THEMES[theme_name] = palette
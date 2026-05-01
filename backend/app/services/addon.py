"""PromptAddOn Injection Module for Promptee.

Provides modular, metric-aligned suffixes that are dynamically injected
into the base prompt payload based on the user's tradeoff preference.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PromptAddOn:
    """An immutable prompt addon that appends a mode-specific instruction."""

    name: str
    mode: str  # "speed" | "quality" | "cost" | "balanced"
    suffix: str
    description: str


BUILTIN_ADDONS: dict[str, PromptAddOn] = {
    "speed": PromptAddOn(
        name="Speed AddOn",
        mode="speed",
        suffix=(
            "\n\nINSTRUCTION: Output only raw code. "
            "No explanations. No commentary. Maximum brevity."
        ),
        description="Optimizes for speed — minimal output, raw code only",
    ),
    "quality": PromptAddOn(
        name="Quality AddOn",
        mode="quality",
        suffix=(
            "\n\nINSTRUCTION: Think step-by-step. Show your reasoning. "
            "Provide thorough, well-structured explanations with examples."
        ),
        description="Optimizes for quality — thorough reasoning and detailed output",
    ),
    "cost": PromptAddOn(
        name="Cost AddOn",
        mode="cost",
        suffix=(
            "\n\nINSTRUCTION: Be concise. Minimize token usage. "
            "Provide the shortest correct answer."
        ),
        description="Optimizes for cost — minimal token usage",
    ),
}


def inject_addon(full_text: str, addon: PromptAddOn) -> str:
    """Append an addon suffix to the prompt text."""
    return full_text + addon.suffix


def get_addons_for_preference(tradeoff_preference: str) -> list[PromptAddOn]:
    """Return applicable AddOns based on the user's tradeoff preference.

    Balanced mode returns no addons — the base prompt is used as-is.
    """
    if tradeoff_preference == "balanced":
        return []
    addon = BUILTIN_ADDONS.get(tradeoff_preference)
    if addon is not None:
        return [addon]
    return []

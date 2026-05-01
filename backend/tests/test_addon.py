"""Tests for PromptAddOn injection module."""

from backend.app.services.addon import (
    BUILTIN_ADDONS,
    PromptAddOn,
    get_addons_for_preference,
    inject_addon,
)


def test_inject_addon_appends_suffix() -> None:
    result = inject_addon("Base prompt.", BUILTIN_ADDONS["speed"])
    assert result.startswith("Base prompt.")
    assert "raw code" in result


def test_get_addons_speed() -> None:
    addons = get_addons_for_preference("speed")
    assert len(addons) == 1
    assert addons[0].mode == "speed"


def test_get_addons_quality() -> None:
    addons = get_addons_for_preference("quality")
    assert len(addons) == 1
    assert addons[0].mode == "quality"


def test_get_addons_balanced_returns_empty() -> None:
    addons = get_addons_for_preference("balanced")
    assert len(addons) == 0


def test_get_addons_unknown_returns_empty() -> None:
    addons = get_addons_for_preference("nonexistent")
    assert len(addons) == 0


def test_addon_is_frozen() -> None:
    addon = BUILTIN_ADDONS["speed"]
    assert isinstance(addon, PromptAddOn)
    try:
        addon.name = "modified"
        assert False, "Should have raised FrozenInstanceError"
    except AttributeError:
        pass

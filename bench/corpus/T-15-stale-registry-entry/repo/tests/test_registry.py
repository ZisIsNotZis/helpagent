"""Tests for the plugin registry."""

from plugins.registry import PluginRegistry


def test_registered_plugin_is_found():
    reg = PluginRegistry()
    plugin = object()
    reg.register("csv", plugin)
    assert reg.lookup("csv") is plugin


def test_unregistered_plugin_is_absent():
    reg = PluginRegistry()
    plugin = object()
    reg.register("legacy-export", plugin, version="1.2")
    reg.unregister("legacy-export")
    assert reg.lookup("legacy-export") is None


def test_lookup_unknown_returns_none():
    assert PluginRegistry().lookup("nope") is None

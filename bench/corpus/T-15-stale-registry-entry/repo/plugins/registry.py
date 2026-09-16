"""Plugin registry: register, unregister, lookup."""


class PluginRegistry:
    """Name-addressable plugin store.

    ``unregister`` must fully remove a plugin: a removed plugin never keeps
    answering lookups.
    """

    def __init__(self) -> None:
        self._plugins: dict[str, object] = {}
        self._meta: dict[str, str] = {}

    def register(self, name: str, plugin: object, *, version: str = "0.0.0") -> None:
        self._plugins[name] = plugin
        self._meta[name] = version

    def unregister(self, name: str) -> None:
        if name in self._meta:
            del self._meta[name]

    def lookup(self, name: str) -> object | None:
        """The plugin registered under ``name``, or ``None`` when absent."""
        return self._plugins.get(name)

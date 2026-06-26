"""Backend-agnostic core: resolves an alias to a reference and delegates.

The core knows nothing about 1Password. It looks an alias up in the registry to
get an opaque reference, then hands that reference to the driver to resolve.

The registry is read through a loader on every lookup, so edits to the registry
file take effect without restarting the server. The driver stays cached.
"""
from .errors import UnknownAlias


class Core:
    def __init__(self, registry_loader, driver):
        self._load_registry = registry_loader
        self._driver = driver

    def read(self, alias):
        reference = self._load_registry().get(alias)
        if reference is None:
            raise UnknownAlias(alias)
        return self._driver.read(reference)

    def aliases(self, prefix=""):
        return sorted(alias for alias in self._load_registry() if alias.startswith(prefix))

"""Backend-agnostic core: maps a logical name to a reference and delegates.

The core knows nothing about 1Password. It looks a name up in the registry to
get an opaque reference, then hands that reference to the driver to resolve.
"""
from .errors import UnknownKey


class Core:
    def __init__(self, registry, driver):
        self._registry = registry
        self._driver = driver

    def read(self, name):
        reference = self._registry.get(name)
        if reference is None:
            raise UnknownKey(name)
        return self._driver.read(reference)

    def keys(self, prefix=""):
        return sorted(name for name in self._registry if name.startswith(prefix))

"""Backend driver interface."""


class Driver:
    """Resolves an opaque reference into a secret value.

    The core never interprets a reference; it passes it to the driver as-is.
    Each backend (1Password Connect Server, a Service Account, another vendor) is one
    implementation of this contract.
    """

    def read(self, reference: str) -> str:
        raise NotImplementedError

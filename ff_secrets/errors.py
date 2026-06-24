"""Error types. All inherit FfSecretsError so the CLI can render them uniformly."""


class FfSecretsError(Exception):
    """Base error carrying a user-facing message."""


class ConfigError(FfSecretsError):
    """Configuration or registry problem."""


class UnknownKey(FfSecretsError):
    """A logical name is not present in the registry."""

    def __init__(self, name):
        super().__init__(f"unknown logical key: {name}")


class DriverError(FfSecretsError):
    """The backend driver failed to resolve a reference."""

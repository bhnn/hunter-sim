from typing import Set

class BuildConfigError(Exception):
    """Raised when there is an error in the build configuration."""
    def __init__(self, invalid_keys: Set):
        message = f"Invalid keys found in build config file: {list(invalid_keys)}"
        super().__init__(message)
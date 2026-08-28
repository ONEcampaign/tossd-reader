"""Python package to access TOSSD activity-level data."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tossd-reader")
except PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["__version__"]

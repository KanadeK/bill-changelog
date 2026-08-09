"""Bill Changelog public package API."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bill-changelog")
except PackageNotFoundError:  # pragma: no cover - source tree and portable archive fallback
    __version__ = "0.1.0"

__all__ = ["__version__"]

"""OpenRevise: Evidence-gated revision infrastructure for high-stakes documents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("openrevise")
except PackageNotFoundError:  # pragma: no cover - only hit when package isn't installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]

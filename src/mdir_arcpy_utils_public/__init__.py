"""mdir-arcpy-utils-public package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .hello import main

try:
	__version__ = version("mdir-arcpy-utils-public")
except PackageNotFoundError:
	__version__ = "unknown"

__all__ = ["main", "__version__"]

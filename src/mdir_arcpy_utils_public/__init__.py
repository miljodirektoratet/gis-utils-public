"""mdir-arcpy-utils-public package."""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

from .hello import main
from .agol_add_users_to_group import agol_add_users_to_group
try:
	__version__ = version("mdir-arcpy-utils-public")
except PackageNotFoundError:
	__version__ = "unknown"

__all__ = ["main", "agol_add_users_to_group", "__version__"]

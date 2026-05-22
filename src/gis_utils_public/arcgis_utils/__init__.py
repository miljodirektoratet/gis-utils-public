"""ArcGIS-dependent utilities.

This subpackage does not import ArcGIS modules during package initialization.
ArcGIS modules are loaded only when explicitly accessed via ``__getattr__``,
so importing ``gis_utils_public`` does not throw errors in environments without ArcGIS.

Example for adding a new module ``module_1.py`` with ``function_a``:
1. Add ``module_1`` to ``TYPE_CHECKING`` imports.
2. Add "module_1" to ``__all__``.
3. No change is needed in ``__getattr__`` because it loads names from ``__all__``.
4. Consumers can then call ``arcgis_utils.module_1.function_a(...)``.
"""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
	# Helps code editors (vscode etc.) recognize available modules without loading ArcGIS code.
	from . import (
		agol_user_admin, 
		yaml_config_arcgis,
		# module_1,  # Example for adding a new module
  )

__all__ = [
	"agol_user_admin",
	"yaml_config_arcgis",
  # "module_1",
	]

def __getattr__(name: str):
	"""Lazily load ArcGIS-dependent modules on first attribute access.

	:param name: Requested attribute name.
	:return: Imported module object.
	:raises AttributeError: If attribute is not part of this package API.
	"""
	if name in __all__:
		return import_module(f"{__name__}.{name}")
	raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

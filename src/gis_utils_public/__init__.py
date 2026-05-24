"""gis-utils-public package.

This package contains GIS utilities for the GIS platform at the Norwegian Environment Agency.
This package is structured to support both open-gis code (that runs in any Python environment)
and ArcGIS-dependent code (that requires ArcGIS Pro or a connection to ArcGIS Online).

PACKAGE STRUCTURE:
==================
- Open-gis code (no ArcGIS dependency):
	- Located in the root package or in subfolders (except arcgis_utils/)
	- Both modules and functions are exported in __init__.py for convenient imports
	- Example import: "from gis_utils_public import main"

- ArcGIS-dependent code (requires ArcGIS Pro/ArcPy):
	- Located in arcgis_utils/: Namespace for all ArcGIS-dependent utilities
	- Example: arcgis_utils/user_admin.py
	- Import as subpackage: "from gis_utils_public import arcgis_utils"
	- Access functions: "arcgis_utils.user_admin.agol_add_users_to_group(...)"
	- IMPORTANT: Do NOT add ArcGIS code to root or other folders to avoid import errors
	- IMPORTANT: Do NOT export ArcGIS code in __init__.py (prevents package import errors in non-ArcGIS environments)

WHY THIS STRUCTURE:
===================
1. Open-gis code in root allows "import gis_utils_public" to work everywhere
   (CI on Ubuntu, non-ArcGIS machines, ArcGIS Pro environments, etc.)
2. ArcGIS-dependent code in arcgis_utils/ is loaded only when explicitly imported
3. Users navigate by folder structure—clear and intuitive

ADDING NEW CODE:
================
1. Open-gis function/module:
	- Create or update module in root (e.g., main.py, utils.py)
	- Import in __init__.py: "from .main import some_function"
	- Add to __all__

2. ArcGIS-dependent function/module:
	- Create module in arcgis_utils/ (e.g., arcgis_utils/new_module.py)
	- Register module in arcgis_utils/__init__.py (for static analysis support while avoiding ArcGIS imports during package initialization)
	- Example: add module_1 in arcgis_utils/__init__.py, then call arcgis_utils.module_1.function_a(...)
	- Users import directly: "from gis_utils_public.arcgis_utils.new_module import new_function"
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

# OPEN-GIS IMPORTS (safe on all platforms)
from .main import main
from .yaml_config import read_yml_config

# ArcGIS SUBPACKAGE (imported as namespace, not eagerly loaded)
# NOTE: Do NOT import specific functions or modules from arcgis_utils here—
# this avoids ArcGIS import errors in non-ArcGIS environments.
from . import arcgis_utils

# Package version
try:
  __version__ = version("gis-utils-public")
except PackageNotFoundError:
  __version__ = "unknown"

# Public API
__all__ = ["main", "read_yml_config", "arcgis_utils", "__version__"]

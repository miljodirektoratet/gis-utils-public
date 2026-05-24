"""ArcGIS Pro runtime and project access checks."""

import logging
import time
from typing import Any

import arcpy

LOGGER = logging.getLogger(__name__)

# --- Shared helpers ---


# --- Helpers for checking ArcGIS Runtime env and project/layer access ---
def check_arcgispro_project_is_closed(aprx_path: str) -> bool:
    """
    Check if the ArcGIS project is accessible and not locked by ArcGIS Pro.

    Tries to open the project; if locked/read-only, prompts user to wait or stop.

    :param aprx_path: Path to ArcGIS Pro project file (.aprx).
    :return: True if project is accessible, False if user chose to stop.
    """
    try:
        test_aprx = arcpy.mp.ArcGISProject(aprx_path)
        is_locked = test_aprx.isReadOnly
        del test_aprx

        if is_locked:
            LOGGER.info("Project is locked or read-only.")
            while True:
                response = (
                    input("  wait and retry / stop? [wait/stop]: ").lower().strip()
                )
                if response == "wait":
                    LOGGER.info("  Waiting 30 seconds...")
                    time.sleep(30)
                    return check_arcgispro_project_is_closed(aprx_path)  # Retry
                elif response == "stop":
                    LOGGER.info("  Stopping pipeline.")
                    return False
                else:
                    LOGGER.info("  Invalid response. Enter 'wait' or 'stop'.")
        return True
    except Exception as e:
        LOGGER.error("Error accessing project: %s", e)
        return False


def report_project_metadata(
    aprx: Any, map_name: str | None = None, label: str = "Project metadata"
) -> None:
    """Report project metadata for one map or all maps.

    :param aprx: ArcGISProject object or APRX file path.
    :param map_name: Optional map name filter. If None, all maps are reported.
    :param label: Header label for the metadata report.
    :return: None.
    """
    created_local_project = False

    if isinstance(aprx, str):
        aprx = arcpy.mp.ArcGISProject(aprx)
        created_local_project = True
    elif not hasattr(aprx, "listMaps"):
        raise TypeError("aprx must be an ArcGISProject object or APRX path string")
    if map_name is not None and (not isinstance(map_name, str) or not map_name.strip()):
        raise ValueError("map_name must be None or a non-empty string")

    try:
        print("\n--- [%s] ---" % label)
        print("  path: %s" % aprx.filePath)
        print("  is_read_only: %s" % aprx.isReadOnly)
        print("  map_count: %s" % len(aprx.listMaps()))
        if map_name is None:
            target_maps = aprx.listMaps()
        else:
            target_maps = aprx.listMaps(map_name)

        if map_name is None:
            print("  Metadata report: ALL")
        else:
            print("  Metadata report:  %s" % map_name)

        if not target_maps:
            if map_name is None:
                print("  -> No maps found in project.")
            else:
                print("  -> No map found with this name.")
            return

        for m in target_maps:
            print("  MAP: %s" % m.name)
            print("    layer_count: %s" % len(m.listLayers()))

            for lyr in m.listLayers():
                if lyr.isGroupLayer or lyr.isBasemapLayer:
                    continue

                try:
                    fields = arcpy.ListFields(lyr)
                    col_count = len(fields) if fields else 0
                    print("      [-]: %s [fields: %s]" % (lyr.name, col_count))
                except Exception:
                    print("      [-]: %s [fields: N/A]" % lyr.name)
    finally:
        print("-" * 50)
        if created_local_project:
            del aprx

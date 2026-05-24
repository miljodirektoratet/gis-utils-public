"""ArcGIS Pro runtime and project access checks."""

import logging
import os
import time
from datetime import datetime
from typing import Any, Callable

import arcpy

LOGGER = logging.getLogger(__name__)

# --- Shared helpers ---


def _clear_workspace_cache() -> None:
    """Clear ArcGIS workspace cache in a best-effort way.

    :return: None.
    """
    try:
        arcpy.ClearWorkspaceCache_management()
        LOGGER.info("ArcGIS workspace cache cleared.")
    except Exception as exc:
        LOGGER.warning("Failed to clear ArcGIS workspace cache: %s", exc)


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
            LOGGER.error("Project is locked or read-only.")
            while True:
                response = (
                    input("  wait and retry / stop? [wait/stop]: ").lower().strip()
                )
                if response == "wait":
                    LOGGER.info("  Waiting 30 seconds...")
                    time.sleep(30)
                    return check_arcgispro_project_is_closed(aprx_path)  # Retry
                elif response == "stop":
                    LOGGER.error("  Stopping pipeline.")
                    return False
                else:
                    LOGGER.info("  Invalid response. Enter 'wait' or 'stop'.")
        
        LOGGER.info("Project is accessible and writable check passed (isReadOnly=False).")
        return True
    except Exception as e:
        LOGGER.error("Error accessing project: %s", e)
        return False


def save_and_close_arcgispro_project(
    aprx: Any,
    save_mode: str = "overwrite",
    copy_path: str | None = None,
    aprx_dir: str | None = None,
    data_product: str | None = None,
    stop_requested: bool = False,
    clear_workspace_cache: bool = True,
) -> dict[str, Any]:
    """Save ArcGIS project according to mode and release project references.

    Save modes:
    - ``overwrite``: Save in place if writable; if read-only, skip save.
    - ``copy``: Save a copy to ``copy_path`` or ``<aprx_dir>/<data_product>_copy.aprx``.
    - ``none``: Do not save.

    :param aprx: ArcGISProject object.
    :param save_mode: Save mode value.
    :param copy_path: Optional explicit copy target path.
    :param aprx_dir: APRX directory used when building default copy path.
    :param data_product: Data product name used when building default copy path.
    :param stop_requested: If True, skip save operations.
    :param clear_workspace_cache: If True, clear ArcGIS workspace cache after close.
    :return: Result dictionary with ``APRX``, ``SAVED``, and ``COPY_PATH``.
    """
    result = {
        "APRX": None,
        "SAVED": False,
        "COPY_PATH": copy_path,
    }

    if aprx is None:
        return result

    normalized_mode = str(save_mode).strip().lower()

    try:
        if bool(stop_requested):
            LOGGER.info("Stop requested; skipping save.")
        elif normalized_mode == "none":
            LOGGER.info("SAVE_MODE=none; skipping save.")
        elif normalized_mode == "overwrite":
            if aprx.isReadOnly:
                LOGGER.info("Project is read-only; skipping in-place save.")
            else:
                aprx.save()
                result["SAVED"] = True
        elif normalized_mode == "copy":
            if not result["COPY_PATH"]:
                if not isinstance(aprx_dir, str) or not aprx_dir.strip():
                    raise ValueError("aprx_dir is required when save_mode='copy'")
                if not isinstance(data_product, str) or not data_product.strip():
                    raise ValueError("data_product is required when save_mode='copy'")
                result["COPY_PATH"] = os.path.join(aprx_dir, f"{data_product}_copy.aprx")
            aprx.saveACopy(result["COPY_PATH"])
            result["SAVED"] = True
        else:
            raise ValueError("save_mode must be one of: overwrite, copy, none")
    finally:
        del aprx
        if bool(clear_workspace_cache):
            _clear_workspace_cache()

    return result


def report_project_metadata(
    aprx: Any,
    map_name: str | None = None,
    label: str = "Project metadata",
    emit: Callable[[str], None] | None = None,
    include_timestamp: bool = True,
    timestamp_format: str = "%d.%m.%Y %H:%M:%S",
) -> None:
    """Report project metadata for one map or all maps.

    :param aprx: ArcGISProject object or APRX file path.
    :param map_name: Optional map name filter. If None, all maps are reported.
    :param label: Header label for the metadata report.
    :param emit: Optional output function. Defaults to ``print``.
    :param include_timestamp: Whether to append timestamp to report header label.
    :param timestamp_format: Datetime format used when ``include_timestamp`` is True.
    :return: None.
    """
    created_local_project = False
    out_msg = emit if callable(emit) else print

    if isinstance(aprx, str):
        aprx = arcpy.mp.ArcGISProject(aprx)
        created_local_project = True
    elif not hasattr(aprx, "listMaps"):
        raise TypeError("aprx must be an ArcGISProject object or APRX path string")
    if map_name is not None and (not isinstance(map_name, str) or not map_name.strip()):
        raise ValueError("map_name must be None or a non-empty string")

    header_label = label
    if include_timestamp:
        timestamp = datetime.now().strftime(timestamp_format)
        header_label = f"{label} ({timestamp})"

    try:
        out_msg("\n--- [%s] ---" % header_label)
        out_msg("  path: %s" % aprx.filePath)
        out_msg("  is_read_only: %s" % aprx.isReadOnly)
        out_msg("  map_count: %s" % len(aprx.listMaps()))
        if map_name is None:
            target_maps = aprx.listMaps()
        else:
            target_maps = aprx.listMaps(map_name)

        if map_name is None:
            out_msg("  Metadata report: ALL")
        else:
            out_msg("  Metadata report:  %s" % map_name)

        if not target_maps:
            if map_name is None:
                out_msg("  -> No maps found in project.")
            else:
                out_msg("  -> No map found with this name.")
            return

        for m in target_maps:
            out_msg("  MAP: %s" % m.name)
            out_msg("    layer_count: %s" % len(m.listLayers()))

            for lyr in m.listLayers():
                if lyr.isGroupLayer or lyr.isBasemapLayer:
                    continue

                try:
                    fields = arcpy.ListFields(lyr)
                    col_count = len(fields) if fields else 0
                    out_msg("      [-]: %s [fields: %s]" % (lyr.name, col_count))
                except Exception:
                    out_msg("      [-]: %s [fields: N/A]" % lyr.name)
    finally:
        out_msg("-" * 50)
        if created_local_project:
            del aprx

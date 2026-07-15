"""ArcGIS Pro project lifecycle and metadata utilities.

Public functions:
- check_arcgispro_project_writable: Verify that an APRX can be opened for writing.
- save_and_close_arcgispro_project: Save APRX by mode and release references.
- report_arcgispro_project_metadata: Print/read basic project and layer metadata.
"""

import logging
import os
import time
from datetime import datetime
from typing import Any, Callable

import arcpy  # type: ignore

LOGGER = logging.getLogger(__name__)


def _extract_service_id(cim_obj: Any) -> int | None:
    """Extract service id from CIM object when present.

    :param cim_obj: CIM object from layer/table definition.
    :return: Service id value or ``None`` if unavailable.
    """
    if cim_obj is None:
        return None

    candidate_attrs = (
        "serviceLayerId",
        "serviceLayerID",
        "serviceTableId",
        "serviceTableID",
    )
    for attr_name in candidate_attrs:
        attr_value = getattr(cim_obj, attr_name, None)
        if attr_value is None:
            continue
        try:
            return int(attr_value)
        except Exception:
            continue
    return None


def _format_visible_total_fields_for_layer(layer_obj: Any) -> str:
    """Return visible/total-layer and total-source field count for one feature layer.

    :param layer_obj: ArcGIS layer object.
    :return: Field count string as ``<visible>/<total_layer> (<total_source>)`` or ``N/A``.
    """
    source_total_fields: int | None = None
    try:
        describe_result = arcpy.da.Describe(layer_obj.dataSource)
        physical_fields = (
            describe_result.get("fields") if isinstance(describe_result, dict) else None
        )
        source_total_fields = len(physical_fields) if physical_fields else 0
    except Exception:
        source_total_fields = None

    layer_total_fields: int | None = None
    try:
        layer_fields = arcpy.ListFields(layer_obj)
        layer_total_fields = len(layer_fields) if layer_fields else 0
    except Exception:
        layer_total_fields = None

    if layer_total_fields is None and source_total_fields is None:
        return "N/A"

    if layer_total_fields is None:
        layer_total_fields = source_total_fields
    if source_total_fields is None:
        source_total_fields = layer_total_fields

    try:
        layer_cim = layer_obj.getDefinition("V3")
        feature_table = getattr(layer_cim, "featureTable", None)
        field_descriptions = (
            getattr(feature_table, "fieldDescriptions", None)
            if feature_table is not None
            else None
        )

        if isinstance(field_descriptions, list) and field_descriptions:
            visible_fields = 0
            for field_description in field_descriptions:
                if bool(getattr(field_description, "visible", True)):
                    visible_fields += 1
            return "%s/%s (%s)" % (
                visible_fields,
                layer_total_fields,
                source_total_fields,
            )
    except Exception:
        pass

    return "%s/%s (%s)" % (
        layer_total_fields,
        layer_total_fields,
        source_total_fields,
    )


def _format_total_fields_for_table(table_obj: Any) -> str:
    """Return visible/total field count string for one standalone table.

    Standalone tables do not use per-field visibility in this pipeline, so
    visible count equals total count.

    :param table_obj: ArcGIS standalone table object.
    :return: Field count string as ``<visible>/<total>`` or ``N/A``.
    """
    source_candidate = getattr(table_obj, "dataSource", None)
    if not isinstance(source_candidate, str) or not source_candidate.strip():
        source_candidate = getattr(table_obj, "catalogPath", None)

    try:
        if source_candidate is not None:
            describe_result = arcpy.da.Describe(source_candidate)
        else:
            describe_result = arcpy.da.Describe(table_obj)
        physical_fields = (
            describe_result.get("fields") if isinstance(describe_result, dict) else None
        )
        total_fields = len(physical_fields) if physical_fields else 0
        return "%s/%s" % (total_fields, total_fields)
    except Exception:
        try:
            if source_candidate is not None:
                fields = arcpy.ListFields(source_candidate)
            else:
                fields = arcpy.ListFields(table_obj)
            total_fields = len(fields) if fields else 0
            return "%s/%s" % (total_fields, total_fields)
        except Exception:
            return "N/A"


def _clear_arcgispro_workspace_cache() -> None:
    """Clear ArcGIS Pro workspace cache.

    :return: None.
    """
    try:
        arcpy.ClearWorkspaceCache_management()
    except Exception as exc:
        LOGGER.warning("Failed to clear ArcGIS workspace cache: %s", exc)


def check_arcgispro_project_writable(aprx_path: str) -> bool:
    """Check if an ArcGIS Pro project is writable.

    Tries to open the project. If locked/read-only, prompts user to wait or stop.

    :param aprx_path: Path to ArcGIS Pro project file (.aprx).
    :return: True if project is writable, False if user chose to stop.
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
                    return check_arcgispro_project_writable(aprx_path)
                if response == "stop":
                    LOGGER.error("  Stopping pipeline.")
                    return False
                LOGGER.info("  Invalid response. Enter 'wait' or 'stop'.")

        LOGGER.debug(
            "Project is accessible and writable check passed (isReadOnly=False)."
        )
        return True
    except Exception as exc:
        LOGGER.error("Error accessing project: %s", exc)
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
    saved_path: str | None = None

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
                saved_path = getattr(aprx, "filePath", None)
        elif normalized_mode == "copy":
            if not result["COPY_PATH"]:
                if not isinstance(aprx_dir, str) or not aprx_dir.strip():
                    raise ValueError("aprx_dir is required when save_mode='copy'")
                if not isinstance(data_product, str) or not data_product.strip():
                    raise ValueError("data_product is required when save_mode='copy'")
                result["COPY_PATH"] = os.path.join(
                    aprx_dir, f"{data_product}_copy.aprx"
                )
            aprx.saveACopy(result["COPY_PATH"])
            result["SAVED"] = True
            saved_path = (
                result["COPY_PATH"] if isinstance(result["COPY_PATH"], str) else None
            )
        else:
            raise ValueError("save_mode must be one of: overwrite, copy, none")

        if result["SAVED"] and isinstance(saved_path, str) and saved_path.strip():
            LOGGER.info("Project saved to path: %s", saved_path)
    finally:
        del aprx
        if bool(clear_workspace_cache):
            _clear_arcgispro_workspace_cache()

    return result


def report_arcgispro_project_metadata(
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

        for map_obj in target_maps:
            out_msg("  MAP: %s" % map_obj.name)
            map_layers = [
                layer_obj
                for layer_obj in map_obj.listLayers()
                if not layer_obj.isGroupLayer and not layer_obj.isBasemapLayer
            ]
            map_tables = map_obj.listTables()
            out_msg("    layer_count: %s" % len(map_layers))

            for layer_obj in map_layers:
                service_id = "-"
                try:
                    layer_cim = layer_obj.getDefinition("V3")
                    extracted = _extract_service_id(layer_cim)
                    if extracted is not None:
                        service_id = str(extracted)
                except Exception:
                    pass

                fields_text = _format_visible_total_fields_for_layer(layer_obj)
                out_msg(
                    "      [%s]: %s [fields: %s]"
                    % (service_id, layer_obj.name, fields_text)
                )

            out_msg("    table_count: %s" % len(map_tables))
            for table_obj in map_tables:
                service_id = "-"
                try:
                    table_cim = table_obj.getDefinition("V3")
                    extracted = _extract_service_id(table_cim)
                    if extracted is not None:
                        service_id = str(extracted)
                except Exception:
                    pass

                fields_text = _format_total_fields_for_table(table_obj)
                out_msg(
                    "      [%s]: %s [fields: %s]"
                    % (service_id, table_obj.name, fields_text)
                )
    finally:
        out_msg("-" * 50)
        if created_local_project:
            del aprx

"""Module for ArcGIS Pro map-related actions:
- set_map_metadata_from_config: Apply map metadata values when metadata editing is available.
"""
import logging
import os

from ..config import read_yml_config

LOGGER = logging.getLogger(__name__)

def set_map_metadata_from_config(map_obj, map_metadata_cfg):
    """Apply map metadata values when metadata editing is available."""
    try:
        md = map_obj.metadata
    except Exception as exc:
        print(f"  -> Metadata is not accessible in this environment: {exc}")
        return

    try:
        if map_metadata_cfg.get("title"):
            md.title = map_metadata_cfg.get("title")
        tags = map_metadata_cfg.get("tags")
        if isinstance(tags, list):
            md.tags = ", ".join(str(t) for t in tags if t)
        elif isinstance(tags, str):
            md.tags = tags
        if map_metadata_cfg.get("summary"):
            md.summary = map_metadata_cfg.get("summary")
        if map_metadata_cfg.get("description"):
            md.description = map_metadata_cfg.get("description")
        if map_metadata_cfg.get("credits"):
            md.credits = map_metadata_cfg.get("credits")
        if map_metadata_cfg.get("license"):
            md.accessConstraints = map_metadata_cfg.get("license")
        map_obj.metadata = md
        print("  -> Map metadata updated from config.")
    except Exception as exc:
        print(f"  -> Failed to set metadata: {exc}")

def enable_unique_numeric_ids(map_obj):
    """Enable map-level service layer IDs for publishing when supported."""
    try:
        map_cim = map_obj.getDefinition("V3")
        if hasattr(map_cim, "useServiceLayerIDs"):
            map_cim.useServiceLayerIDs = True
            map_obj.setDefinition(map_cim)
            return True

        for attr in [
            "allowAssignmentOfUniqueNumericIds",
            "allowAssignmentOfUniqueNumericIDs",
            "allowAssigningUniqueNumericIds",
            "allowAssigningUniqueNumericIDs",
        ]:
            if hasattr(map_cim, attr):
                setattr(map_cim, attr, True)
                map_obj.setDefinition(map_cim)
                return True

        return False
    except Exception as ex:
        print(f"Error enabling unique numeric IDs: {ex}")
        return False
"""ArcGIS Pro map-related helper functions.

Public functions:
- set_map_metadata_from_config: Apply map metadata values from configuration.
- enable_unique_numeric_ids: Enable stable numeric layer IDs for publishing.
"""

import logging
from typing import Any, Mapping

LOGGER = logging.getLogger(__name__)


def set_map_metadata_from_config(
    map_obj: Any, map_metadata_cfg: Mapping[str, Any]
) -> None:
    """Apply map metadata values when metadata editing is available.

    :param map_obj: ArcGIS Pro map object with a ``metadata`` property.
    :param map_metadata_cfg: Metadata values from configuration.
    :return: None.
    """
    try:
        md = map_obj.metadata
    except Exception as exc:
        LOGGER.warning("Metadata is not accessible in this environment: %s", exc)
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
        LOGGER.info("Map metadata updated from config.")
    except Exception as exc:
        LOGGER.error("Failed to set metadata: %s", exc)


def enable_unique_numeric_ids(map_obj: Any) -> bool:
    """Enable map-level service layer IDs for publishing when supported.

    :param map_obj: ArcGIS Pro map object.
    :return: ``True`` if setting was applied, otherwise ``False``.
    """
    try:
        map_cim = map_obj.getDefinition("V3")
        if hasattr(map_cim, "useServiceLayerIDs"):
            map_cim.useServiceLayerIDs = True
            map_obj.setDefinition(map_cim)
            LOGGER.debug("Unique numeric IDs enabled via 'useServiceLayerIDs'.")
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
                LOGGER.debug("Unique numeric IDs enabled via CIM attribute '%s'.", attr)
                return True

        return False
    except Exception as exc:
        LOGGER.error("Failed to enable unique numeric IDs: %s", exc)
        return False

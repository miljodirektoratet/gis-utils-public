"""ArcGIS Pro layer-related helper functions.

Public functions:
- construct_sde_dataset_path: Build dataset path candidates from layer config.
- add_layer_from_sde: Add one layer from SDE source.
- add_layers_from_config_sde_to_map: Add YAML-configured layers from SDE to map.
- resolve_lyrx_path: Resolve LYRX path for one layer.
- apply_lyrx_to_layer: Apply LYRX transfer to a map layer.
- apply_lyrx_to_map_layers_from_config: Apply LYRX transfer to YAML-defined map layers.
- ensure_cim_field_descriptions: Init CIM field descriptions from source fields.
- reorder_layer_fields: Reorder fields using config-first ordering.
- set_only_fields_visible: Apply visibility from configured field list.
- check_and_update_service_id: Check and update service layer id.
- configure_display_field: Configure display field from layer config.
- configure_popup_fields_from_visible: Configure popup fields from visible config.
"""

import logging
import os
from typing import Any

from .yaml_config_arcgis import (
	iter_map_service_layer_entries,
	resolve_layer_sde_connection_path,
)

LOGGER = logging.getLogger(__name__)


# Use one result format for add layer in all cases.
def _create_add_layer_from_sde_result(
	layer_name: str,
	sde_connection_path: str | None,
) -> dict[str, Any]:
	"""Build default result object for add-layer-from-SDE operations.

	:param layer_name: Layer name.
	:param sde_connection_path: Resolved SDE path if available.
	:return: Default result dictionary with stable schema.
	"""
	return {
		"layer_name": layer_name,
		"sde_connection": sde_connection_path,
		"dataset_path": None,
		"tried_paths": [],
		"added": False,
		"skipped": False,
		"error": None,
	}


# Get existing layer names once so reruns do not add duplicates.
def _get_existing_map_layer_names(map_obj: Any) -> set[str]:
	"""Return case-insensitive set of existing layer names in map.

	:param map_obj: ArcGIS Pro map object.
	:return: Set of existing layer names normalized with ``casefold()``.
	"""
	existing_names: set[str] = set()
	for layer in map_obj.listLayers():
		layer_name = getattr(layer, "name", None)
		if isinstance(layer_name, str) and layer_name.strip():
			existing_names.add(layer_name.strip().casefold())
	return existing_names


# Use one result format for LYRX path checks.
def _create_lyrx_path_resolution_result(
	layer_name: str,
	lyrx_dir: str,
	allow_suffix_match: bool,
	recurse_subfolders: bool,
) -> dict[str, Any]:
	"""Build default result object for LYRX path resolution.

	:param layer_name: Layer name.
	:param lyrx_dir: Root LYRX directory.
	:param allow_suffix_match: Whether suffix matching is enabled.
	:param recurse_subfolders: Whether recursive lookup is enabled.
	:return: Default result dictionary with stable schema.
	"""
	return {
		"layer_name": layer_name,
		"lyrx_dir": lyrx_dir,
		"recurse_subfolders": recurse_subfolders,
		"allow_suffix_match": allow_suffix_match,
		"lyrx_path": None,
		"match_type": None,
		"candidate_count": 0,
		"candidate_paths": [],
	}


# Use one result format for apply LYRX.
def _create_apply_lyrx_to_layer_result(
	layer_name: str,
	transfer_mode: str,
	resolve_result: dict[str, Any],
) -> dict[str, Any]:
	"""Build default result object for apply-LYRX operations.

	:param layer_name: Layer name.
	:param transfer_mode: LYRX transfer mode.
	:param resolve_result: LYRX path resolution result.
	:return: Default result dictionary with stable schema.
	"""
	return {
		"layer_name": layer_name,
		"transfer_mode": transfer_mode,
		"lyrx_path": resolve_result.get("lyrx_path"),
		"match_type": resolve_result.get("match_type"),
		"candidate_count": resolve_result.get("candidate_count"),
		"applied": False,
		"error": None,
	}


def construct_sde_dataset_path(
	sde_connection_path: str,
	layer_config: dict[str, Any],
) -> tuple[str, list[str]]:
	"""Build and resolve ArcGIS dataset path from layer source config.

	:param sde_connection_path: Resolved SDE connection file path.
	:param layer_config: Per-layer config dictionary.
	:return: Tuple of resolved dataset path candidate and all tried paths.
	:raises ValueError: If required dataset config is missing.
	"""
	import arcpy

	source_cfg = (layer_config or {}).get("source", {})
	feature_dataset = source_cfg.get("feature_dataset")
	dataset = source_cfg.get("dataset")

	if not isinstance(dataset, str) or not dataset.strip():
		raise ValueError("Missing or invalid 'source.dataset' in layer config")

	dataset = dataset.strip()
	candidate_paths: list[str] = []
	if isinstance(feature_dataset, str) and feature_dataset.strip():
		candidate_paths.append(
			os.path.join(sde_connection_path, feature_dataset.strip(), dataset)
		)
	candidate_paths.append(os.path.join(sde_connection_path, dataset))

	for candidate_path in candidate_paths:
		if arcpy.Exists(candidate_path):
			return candidate_path, candidate_paths

	return candidate_paths[0], candidate_paths


def add_layer_from_sde(
	map_obj: Any,
	layer_name: str,
	sde_connection_path: str,
	layer_config: dict[str, Any],
) -> dict[str, Any]:
	"""Add one layer to map from SDE source using layer config.

	:param map_obj: ArcGIS Pro map object.
	:param layer_name: Target layer name from configuration.
	:param sde_connection_path: Resolved SDE connection file path.
	:param layer_config: Per-layer config dictionary.
	:return: Result dictionary for logging/reporting.
	"""
	import arcpy

	result = _create_add_layer_from_sde_result(
		layer_name=layer_name,
		sde_connection_path=sde_connection_path,
	)

	try:
		dataset_path, tried_paths = construct_sde_dataset_path(
			sde_connection_path=sde_connection_path,
			layer_config=layer_config,
		)
		result["dataset_path"] = dataset_path
		result["tried_paths"] = tried_paths

		if not arcpy.Exists(dataset_path):
			result["error"] = "Source dataset was not found"
			return result

		added_obj = map_obj.addDataFromPath(dataset_path)
		if hasattr(added_obj, "name"):
			added_obj.name = layer_name

		result["added"] = True
		return result
	except Exception as exc:
		result["error"] = str(exc)
		return result


def add_layers_from_config_sde_to_map(
	map_obj: Any,
	service_def_config: dict[str, Any],
	env: str = "test",
	fallback_sde_path: str | None = None,
) -> dict[str, Any]:
	"""Add all YAML-defined layers from SDE to the target map.

	:param map_obj: ArcGIS Pro map object.
	:param service_def_config: Full map service definition config dictionary.
	:param env: Environment key for resolving map-level SDE connection.
	:param fallback_sde_path: Optional fallback SDE path.
	:return: Summary dictionary with per-layer results.
	"""
	layer_entries = iter_map_service_layer_entries(service_def_config)
	results: list[dict[str, Any]] = []
	existing_layer_names = _get_existing_map_layer_names(map_obj)

	LOGGER.info("Add layers from SDE in config order")

	for layer_name, layer_config in layer_entries:
		normalized_layer_name = layer_name.strip().casefold()
		if normalized_layer_name in existing_layer_names:
			layer_result = _create_add_layer_from_sde_result(
				layer_name=layer_name,
				sde_connection_path=None,
			)
			layer_result["skipped"] = True
			LOGGER.info("-> Skip adding layer '%s': layer already exists in map", layer_name)
			results.append(layer_result)
			continue

		LOGGER.info("-> Add layer from SDE source: %s", layer_name)
		try:
			sde_connection_path = resolve_layer_sde_connection_path(
				service_def_config=service_def_config,
				layer_config=layer_config,
				env=env,
				fallback_path=fallback_sde_path,
			)
		except Exception as exc:
			layer_result = _create_add_layer_from_sde_result(
				layer_name=layer_name,
				sde_connection_path=None,
			)
			layer_result["error"] = str(exc)
			LOGGER.warning("-> Could not resolve sde_connection for '%s': %s", layer_name, exc)
			results.append(layer_result)
			continue

		if not os.path.exists(sde_connection_path):
			LOGGER.warning("-> SDE connection file was not found: %s", sde_connection_path)

		layer_result = add_layer_from_sde(
			map_obj=map_obj,
			layer_name=layer_name,
			sde_connection_path=sde_connection_path,
			layer_config=layer_config,
		)
		if layer_result.get("added"):
			existing_layer_names.add(normalized_layer_name)
			LOGGER.info("-> Added layer '%s' from %s", layer_name, layer_result.get("dataset_path"))
		elif layer_result.get("skipped"):
			LOGGER.info("-> Skipped layer '%s'", layer_name)
		else:
			LOGGER.warning("-> Failed adding layer '%s': %s", layer_name, layer_result.get("error"))
		results.append(layer_result)

	added_count = sum(1 for result in results if bool(result.get("added")))
	skipped_count = sum(1 for result in results if bool(result.get("skipped")))
	LOGGER.info(
		"-> Added %d/%d layer(s) to map (skipped existing: %d)",
		added_count,
		len(layer_entries),
		skipped_count,
	)

	return {
		"layer_results": results,
		"layer_total": len(layer_entries),
		"layers_added_count": added_count,
		"layers_skipped_count": skipped_count,
	}


def _iter_lyrx_file_paths(lyrx_dir: str, recurse_subfolders: bool) -> list[str]:
	"""Return all .lyrx file paths under a directory.

	:param lyrx_dir: Root LYRX directory.
	:param recurse_subfolders: Whether to recurse into subfolders.
	:return: Sorted list of absolute .lyrx file paths.
	"""
	if not isinstance(lyrx_dir, str) or not lyrx_dir.strip():
		return []

	root_dir = os.path.abspath(lyrx_dir)
	if not os.path.isdir(root_dir):
		return []

	paths: list[str] = []
	if recurse_subfolders:
		for walk_root, _, file_names in os.walk(root_dir):
			for file_name in file_names:
				if isinstance(file_name, str) and file_name.lower().endswith(".lyrx"):
					paths.append(os.path.join(walk_root, file_name))
	else:
		for file_name in os.listdir(root_dir):
			candidate = os.path.join(root_dir, file_name)
			if os.path.isfile(candidate) and file_name.lower().endswith(".lyrx"):
				paths.append(candidate)

	return sorted(paths, key=lambda path: path.lower())


# Scan LYRX files once and reuse the list.
def _build_lyrx_lookup_index(all_lyrx_files: list[str]) -> dict[str, list[str]]:
	"""Build case-insensitive lookup index for LYRX filenames.

	:param all_lyrx_files: Absolute LYRX file paths.
	:return: Mapping of lower-cased filename to sorted path list.
	"""
	index: dict[str, list[str]] = {}
	for path in all_lyrx_files:
		file_name = os.path.basename(path).lower()
		index.setdefault(file_name, []).append(path)

	for file_name in index:
		index[file_name] = sorted(index[file_name], key=lambda item: item.lower())

	return index


# Find LYRX path from saved list to avoid extra scans.
def _resolve_lyrx_path_from_index(
	layer_name: str,
	lyrx_dir: str,
	allow_suffix_match: bool,
	recurse_subfolders: bool,
	lyrx_lookup_index: dict[str, list[str]],
) -> dict[str, Any]:
	"""Resolve LYRX path using prebuilt filename index.

	:param layer_name: Layer name in the map/YAML config.
	:param lyrx_dir: Root LYRX directory.
	:param allow_suffix_match: Whether to allow ``<layer_name>_*.lyrx`` fallback.
	:param recurse_subfolders: Whether LYRX lookup recurses into subfolders.
	:param lyrx_lookup_index: Mapping of lower-cased filename to path list.
	:return: Resolution dictionary with selected path and match metadata.
	"""
	normalized_name = str(layer_name or "").strip().lower()
	result = _create_lyrx_path_resolution_result(
		layer_name=layer_name,
		lyrx_dir=lyrx_dir,
		allow_suffix_match=allow_suffix_match,
		recurse_subfolders=recurse_subfolders,
	)

	if not normalized_name:
		return result

	exact_file_name = f"{normalized_name}.lyrx"
	exact_matches = lyrx_lookup_index.get(exact_file_name, [])
	if exact_matches:
		selected = exact_matches[0]
		if len(exact_matches) > 1:
			LOGGER.warning(
				"-> Multiple exact LYRX matches for '%s'. Using first alphabetically: %s",
				layer_name,
				selected,
			)
		result.update(
			{
				"lyrx_path": selected,
				"match_type": "exact",
				"candidate_count": len(exact_matches),
				"candidate_paths": exact_matches,
			}
		)
		return result

	if allow_suffix_match:
		suffix_prefix = f"{normalized_name}_"
		suffix_matches = sorted(
			[
				paths[0]
				for file_name, paths in lyrx_lookup_index.items()
				if file_name.startswith(suffix_prefix)
			],
			key=lambda item: item.lower(),
		)
		if suffix_matches:
			selected = suffix_matches[0]
			if len(suffix_matches) > 1:
				LOGGER.warning(
					"-> Multiple suffix LYRX matches for '%s'. Using first alphabetically: %s",
					layer_name,
					selected,
				)
			result.update(
				{
					"lyrx_path": selected,
					"match_type": "suffix",
					"candidate_count": len(suffix_matches),
					"candidate_paths": suffix_matches,
				}
			)

	return result


def resolve_lyrx_path(
	layer_name: str,
	lyrx_dir: str,
	allow_suffix_match: bool = True,
	recurse_subfolders: bool = True,
) -> dict[str, Any]:
	"""Resolve LYRX path for a layer using strict-first matching.

	Matching strategy:
	- exact: ``<layer_name>.lyrx`` (case-insensitive)
	- suffix: ``<layer_name>_*.lyrx`` (case-insensitive, optional)

	When multiple candidates are found for the selected strategy, the first
	alphabetically sorted path is selected and a warning is logged.

	:param layer_name: Layer name in the map/YAML config.
	:param lyrx_dir: Root LYRX directory.
	:param allow_suffix_match: Whether to allow ``<layer_name>_*.lyrx`` fallback.
	:param recurse_subfolders: Whether LYRX lookup recurses into subfolders.
	:return: Resolution dictionary with selected path and match metadata.
	"""
	all_lyrx_files = _iter_lyrx_file_paths(lyrx_dir, recurse_subfolders)
	lyrx_lookup_index = _build_lyrx_lookup_index(all_lyrx_files)
	return _resolve_lyrx_path_from_index(
		layer_name=layer_name,
		lyrx_dir=lyrx_dir,
		allow_suffix_match=allow_suffix_match,
		recurse_subfolders=recurse_subfolders,
		lyrx_lookup_index=lyrx_lookup_index,
	)


def apply_lyrx_to_layer(
	target_layer: Any,
	layer_name: str,
	lyrx_dir: str,
	transfer_mode: str = "symbology",
	allow_suffix_match: bool = True,
	recurse_subfolders: bool = True,
	lyrx_lookup_index: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
	"""Apply LYRX transfer to an existing map layer.

	Transfer modes:
	- ``symbology``: apply only symbology from LYRX
	- ``all``: apply symbology, definition query, labels and popup settings

	:param target_layer: Target ArcGIS layer object in map.
	:param layer_name: Layer name used for LYRX lookup.
	:param lyrx_dir: Root LYRX directory.
	:param transfer_mode: Transfer mode (``symbology`` or ``all``).
	:param allow_suffix_match: Whether to allow ``<layer_name>_*.lyrx`` fallback.
	:param recurse_subfolders: Whether LYRX lookup recurses into subfolders.
	:param lyrx_lookup_index: Optional prebuilt LYRX lookup index for batch runs.
	:return: Result dictionary for logging/reporting.
	"""
	import arcpy

	mode = str(transfer_mode or "").strip().lower()
	if mode not in {"symbology", "all"}:
		raise ValueError("transfer_mode must be 'symbology' or 'all'")

	if isinstance(lyrx_lookup_index, dict):
		resolve_result = _resolve_lyrx_path_from_index(
			layer_name=layer_name,
			lyrx_dir=lyrx_dir,
			allow_suffix_match=allow_suffix_match,
			recurse_subfolders=recurse_subfolders,
			lyrx_lookup_index=lyrx_lookup_index,
		)
	else:
		resolve_result = resolve_lyrx_path(
			layer_name=layer_name,
			lyrx_dir=lyrx_dir,
			allow_suffix_match=allow_suffix_match,
			recurse_subfolders=recurse_subfolders,
		)

	result = _create_apply_lyrx_to_layer_result(
		layer_name=layer_name,
		transfer_mode=mode,
		resolve_result=resolve_result,
	)

	lyrx_path = resolve_result.get("lyrx_path")
	if not isinstance(lyrx_path, str) or not lyrx_path:
		result["error"] = "No matching LYRX file was found"
		LOGGER.warning(
			"-> LYRX not found for layer '%s' in '%s' (recursive=%s)",
			layer_name,
			lyrx_dir,
			recurse_subfolders,
		)
		return result

	layer_file = None
	try:
		layer_file = arcpy.mp.LayerFile(lyrx_path)
		source_layers = layer_file.listLayers()
		if not source_layers:
			result["error"] = "LYRX has no layers"
			LOGGER.warning("-> LYRX has no layers for '%s': %s", layer_name, lyrx_path)
			return result

		source_layer = next(
			(layer for layer in source_layers if not layer.isGroupLayer),
			source_layers[0],
		)
		arcpy.management.ApplySymbologyFromLayer(target_layer, source_layer)

		if mode == "all":
			if hasattr(source_layer, "definitionQuery") and hasattr(
				target_layer, "definitionQuery"
			):
				source_query = source_layer.definitionQuery
				target_layer.definitionQuery = source_query if source_query is not None else ""

			source_cim = source_layer.getDefinition("V3")
			target_cim = target_layer.getDefinition("V3")
			changed_cim = False

			if hasattr(source_layer, "showLabels") and hasattr(target_layer, "showLabels"):
				target_layer.showLabels = source_layer.showLabels

			if hasattr(source_cim, "labelClasses") and hasattr(target_cim, "labelClasses"):
				setattr(target_cim, "labelClasses", getattr(source_cim, "labelClasses"))
				changed_cim = True

			if hasattr(source_cim, "popupInfo") and hasattr(target_cim, "popupInfo"):
				setattr(target_cim, "popupInfo", getattr(source_cim, "popupInfo"))
				changed_cim = True

			source_ft = getattr(source_cim, "featureTable", None)
			target_ft = getattr(target_cim, "featureTable", None)
			if source_ft is not None and target_ft is not None:
				if hasattr(source_ft, "htmlPopupInfo") and hasattr(
					target_ft, "htmlPopupInfo"
				):
					setattr(target_ft, "htmlPopupInfo", getattr(source_ft, "htmlPopupInfo"))
					changed_cim = True

			if changed_cim:
				target_layer.setDefinition(target_cim)

		result["applied"] = True
		return result
	except Exception as exc:
		result["error"] = str(exc)
		return result
	finally:
		if layer_file is not None:
			del layer_file


def apply_lyrx_to_map_layers_from_config(
	map_obj: Any,
	service_def_config: dict[str, Any],
	lyrx_dir: str,
	transfer_mode: str = "symbology",
	allow_suffix_match: bool = True,
	recurse_subfolders: bool = True,
) -> dict[str, Any]:
	"""Apply LYRX transfer for all YAML-defined layers in a map.

	:param map_obj: ArcGIS Pro map object.
	:param service_def_config: Full map service definition config dictionary.
	:param lyrx_dir: Root LYRX directory.
	:param transfer_mode: Transfer mode (``symbology`` or ``all``).
	:param allow_suffix_match: Whether to allow ``<layer_name>_*.lyrx`` fallback.
	:param recurse_subfolders: Whether LYRX lookup recurses into subfolders.
	:return: Summary dictionary with per-layer transfer results.
	"""
	layer_entries = iter_map_service_layer_entries(service_def_config)
	results: list[dict[str, Any]] = []

	LOGGER.info(
		"Apply LYRX transfer to map layers (mode=%s, allow_suffix_match=%s, recurse_subfolders=%s)",
		transfer_mode,
		allow_suffix_match,
		recurse_subfolders,
	)
	all_lyrx_files = _iter_lyrx_file_paths(lyrx_dir, recurse_subfolders)
	lyrx_lookup_index = _build_lyrx_lookup_index(all_lyrx_files)

	for layer_name, _ in layer_entries:
		target_layers = map_obj.listLayers(layer_name)
		if not target_layers:
			result = _create_apply_lyrx_to_layer_result(
				layer_name=layer_name,
				transfer_mode=transfer_mode,
				resolve_result=_create_lyrx_path_resolution_result(
					layer_name=layer_name,
					lyrx_dir=lyrx_dir,
					allow_suffix_match=allow_suffix_match,
					recurse_subfolders=recurse_subfolders,
				),
			)
			result["error"] = "Target map layer was not found"
			LOGGER.warning("-> Could not find target map layer for LYRX transfer: %s", layer_name)
			results.append(result)
			continue

		if len(target_layers) > 1:
			LOGGER.warning(
				"-> Multiple target map layers found for '%s'. Using first match.",
				layer_name,
			)

		layer_result = apply_lyrx_to_layer(
			target_layer=target_layers[0],
			layer_name=layer_name,
			lyrx_dir=lyrx_dir,
			transfer_mode=transfer_mode,
			allow_suffix_match=allow_suffix_match,
			recurse_subfolders=recurse_subfolders,
			lyrx_lookup_index=lyrx_lookup_index,
		)
		if layer_result.get("applied"):
			LOGGER.info(
				"-> Applied LYRX (%s match) for '%s': %s",
				layer_result.get("match_type"),
				layer_name,
				layer_result.get("lyrx_path"),
			)
		else:
			LOGGER.warning(
				"-> Failed LYRX transfer for '%s': %s",
				layer_name,
				layer_result.get("error"),
			)
		results.append(layer_result)

	applied_count = sum(1 for item in results if bool(item.get("applied")))
	return {
		"layer_results": results,
		"layer_total": len(layer_entries),
		"layers_applied_count": applied_count,
		"transfer_mode": transfer_mode,
		"lyrx_dir": lyrx_dir,
		"allow_suffix_match": allow_suffix_match,
		"recurse_subfolders": recurse_subfolders,
	}


def _normalize_field_name(name: Any) -> str | None:
	"""Normalize field name for robust config-to-layer matching.

	:param name: Raw field name.
	:return: Normalized lower-case field name or None.
	"""
	if not isinstance(name, str):
		return None
	normalized = name.strip().lower()
	if not normalized:
		return None
	if "." in normalized:
		normalized = normalized.split(".")[-1]
	return normalized


def _get_layer_fields_and_descriptions(layer: Any) -> tuple[Any, Any, Any]:
	"""Return layer fields, cim and field descriptions.

	:param layer: ArcGIS layer object.
	:return: Tuple ``(fields, cim, field_descriptions)``.
	"""
	import arcpy

	if layer.isGroupLayer or layer.isBasemapLayer:
		return None, None, None

	try:
		fields = arcpy.ListFields(layer)
		cim = layer.getDefinition("V3")
	except Exception:
		return None, None, None

	feature_table = getattr(cim, "featureTable", None)
	field_descriptions = (
		getattr(feature_table, "fieldDescriptions", None)
		if feature_table is not None
		else None
	)
	return fields, cim, field_descriptions


def _get_layer_field_name_lookup(layer: Any) -> tuple[dict[str, str], str | None]:
	"""Build normalized field-name lookup for one layer.

	:param layer: ArcGIS layer object.
	:return: Tuple ``(lookup, error_message)``.
	"""
	import arcpy

	try:
		fields = arcpy.ListFields(layer)
	except Exception as exc:
		return {}, f"Could not list fields: {exc}"

	lookup: dict[str, str] = {}
	for field in fields:
		actual_name = getattr(field, "name", None)
		if not isinstance(actual_name, str):
			continue
		normalized = _normalize_field_name(actual_name)
		if normalized and normalized not in lookup:
			lookup[normalized] = actual_name

	return lookup, None


def ensure_cim_field_descriptions(layer: Any, set_visible: bool = True) -> tuple[bool, int]:
	"""Initialize layer CIM field descriptions from source fields.

	:param layer: ArcGIS layer object.
	:param set_visible: Whether each new field should be visible.
	:return: Tuple ``(initialized, field_count)``.
	"""
	fields, cim, _ = _get_layer_fields_and_descriptions(layer)
	if fields is None:
		return False, 0

	feature_table = getattr(cim, "featureTable", None)
	if feature_table is None:
		return False, 0

	builder = getattr(cim, "_arc_object", None)
	if builder is None:
		return False, 0

	rebuilt_descriptions = []
	for field in fields:
		field_name = getattr(field, "name", None)
		alias_name = getattr(field, "aliasName", None)
		if not isinstance(field_name, str) or not field_name:
			continue

		fd = builder.createObject("CIMFieldDescription")
		fd.fieldName = field_name
		fd.alias = alias_name if isinstance(alias_name, str) else field_name
		fd.visible = bool(set_visible)
		rebuilt_descriptions.append(fd)

	feature_table.fieldDescriptions = rebuilt_descriptions
	layer.setDefinition(cim)
	return True, len(rebuilt_descriptions)


def reorder_layer_fields(layer: Any, desired_field_order: list[str]) -> int | None:
	"""Reorder layer fields by config-first then remaining alphabetical.

	:param layer: ArcGIS layer object.
	:param desired_field_order: Desired field order from config.
	:return: Reordered field count, 0 if unchanged, or None when unavailable.
	"""
	if not desired_field_order:
		return 0

	_, cim, field_descriptions = _get_layer_fields_and_descriptions(layer)
	if not field_descriptions:
		return None

	field_by_name: dict[str, Any] = {}
	for field_description in field_descriptions:
		raw_name = getattr(field_description, "fieldName", None) or getattr(
			field_description, "name", None
		)
		normalized = _normalize_field_name(raw_name)
		if normalized and normalized not in field_by_name:
			field_by_name[normalized] = field_description

	reordered_descriptions = []
	seen_fields: set[str] = set()

	for field_name in desired_field_order:
		normalized = _normalize_field_name(field_name)
		if normalized in field_by_name:
			reordered_descriptions.append(field_by_name[normalized])
			seen_fields.add(normalized)

	remaining_descriptions = []
	for field_description in field_descriptions:
		raw_name = getattr(field_description, "fieldName", None) or getattr(
			field_description, "name", None
		)
		normalized = _normalize_field_name(raw_name)
		if normalized not in seen_fields:
			remaining_descriptions.append(field_description)

	remaining_descriptions.sort(
		key=lambda field_description: (
			(getattr(field_description, "fieldName", None) or getattr(field_description, "name", "")).lower()
		)
	)
	reordered_descriptions.extend(remaining_descriptions)

	if reordered_descriptions == field_descriptions:
		return 0

	cim.featureTable.fieldDescriptions = reordered_descriptions
	layer.setDefinition(cim)
	return len(reordered_descriptions)


def set_only_fields_visible(
	layer: Any,
	visible_field_names: list[str],
) -> tuple[int, int, int, int, int, list[str]]:
	"""Set visibility so only configured fields are visible.

	:param layer: ArcGIS layer object.
	:param visible_field_names: Configured visible field list.
	:return: Visibility summary tuple.
	"""
	if not visible_field_names:
		return 0, 0, 0, 0, 0, []

	_, cim, field_descriptions = _get_layer_fields_and_descriptions(layer)
	if field_descriptions is None:
		return 0, 0, 0, 0, 0, []

	visible_set = {
		normalized
		for normalized in (_normalize_field_name(name) for name in visible_field_names)
		if normalized
	}

	made_visible = 0
	made_hidden = 0

	for field_description in field_descriptions:
		raw_name = getattr(field_description, "fieldName", None) or getattr(
			field_description, "name", None
		)
		normalized = _normalize_field_name(raw_name)
		should_be_visible = normalized in visible_set
		current_visible = getattr(field_description, "visible", True)

		if should_be_visible and not current_visible:
			field_description.visible = True
			made_visible += 1
		elif not should_be_visible and current_visible:
			field_description.visible = False
			made_hidden += 1

	if made_visible > 0 or made_hidden > 0:
		layer.setDefinition(cim)

	final_visible = 0
	final_hidden = 0
	available_names: set[str] = set()
	for field_description in field_descriptions:
		raw_name = getattr(field_description, "fieldName", None) or getattr(
			field_description, "name", None
		)
		normalized = _normalize_field_name(raw_name)
		if normalized:
			available_names.add(normalized)
		if getattr(field_description, "visible", True):
			final_visible += 1
		else:
			final_hidden += 1

	target_visible = len(visible_set.intersection(available_names))
	missing_config_fields = [
		name
		for name in visible_field_names
		if _normalize_field_name(name) not in available_names
	]

	return (
		made_visible,
		made_hidden,
		final_visible,
		final_hidden,
		target_visible,
		missing_config_fields,
	)


def check_and_update_service_id(layer: Any, expected_service_id: Any) -> tuple[bool, bool]:
	"""Check service layer id and update when needed.

	:param layer: ArcGIS layer object.
	:param expected_service_id: Configured service id.
	:return: Tuple ``(is_correct, was_updated)``.
	"""
	if expected_service_id is None:
		return True, False

	try:
		layer_cim = layer.getDefinition("V3")
		current_id = getattr(layer_cim, "serviceLayerId", None) or getattr(
			layer_cim, "serviceLayerID", None
		)

		if current_id == expected_service_id:
			return True, False

		if hasattr(layer_cim, "serviceLayerId"):
			layer_cim.serviceLayerId = expected_service_id
		else:
			layer_cim.serviceLayerID = expected_service_id

		layer.setDefinition(layer_cim)
		return False, True
	except Exception:
		return False, False


def configure_display_field(
	layer: Any,
	display_field_name: Any,
) -> tuple[Any, bool, str]:
	"""Set display field when configured field exists on layer.

	:param layer: ArcGIS layer object.
	:param display_field_name: Configured display field.
	:return: Tuple ``(is_correct, was_updated, info_message)``.
	"""
	if not isinstance(display_field_name, str) or not display_field_name.strip():
		return None, False, "No display_field configured"

	requested = display_field_name.strip()
	requested_normalized = _normalize_field_name(requested)
	if requested_normalized is None:
		return None, False, "Configured display_field is empty after normalization"

	available_by_normalized, error_message = _get_layer_field_name_lookup(layer)
	if error_message:
		return None, False, error_message

	if requested_normalized not in available_by_normalized:
		return None, False, f"Configured display_field '{requested}' not found in layer fields"

	resolved_field_name = available_by_normalized[requested_normalized]

	try:
		layer_cim = layer.getDefinition("V3")
		feature_table = getattr(layer_cim, "featureTable", None)
		if feature_table is None:
			return None, False, "Layer CIM does not expose featureTable"

		current_display = getattr(feature_table, "displayField", None)
		if _normalize_field_name(current_display) == requested_normalized:
			return True, False, resolved_field_name

		setattr(feature_table, "displayField", resolved_field_name)
		layer.setDefinition(layer_cim)
		return False, True, resolved_field_name
	except Exception as exc:
		return None, False, f"Could not set display field: {exc}"


def configure_popup_fields_from_visible(
	layer: Any,
	visible_field_names: list[str],
) -> tuple[Any, bool, str]:
	"""Configure popup fields from configured visible field order.

	:param layer: ArcGIS layer object.
	:param visible_field_names: Configured visible field list.
	:return: Tuple ``(is_correct, was_updated, info_message)``.
	"""
	import arcpy

	if not isinstance(visible_field_names, list) or not visible_field_names:
		return None, False, "No cols configured"

	normalized_requested: list[str] = []
	seen: set[str] = set()
	for name in visible_field_names:
		normalized = _normalize_field_name(name)
		if normalized and normalized not in seen:
			seen.add(normalized)
			normalized_requested.append(normalized)

	if not normalized_requested:
		return None, False, "No valid field names in cols"

	available_by_normalized, error_message = _get_layer_field_name_lookup(layer)
	if error_message:
		return None, False, error_message

	popup_fields = [
		available_by_normalized[name]
		for name in normalized_requested
		if name in available_by_normalized
	]
	if not popup_fields:
		return None, False, "No configured cols fields were found in layer"

	cim_module = getattr(arcpy, "cim", None)
	if cim_module is None:
		return None, False, "arcpy.cim is not available in this ArcGIS Pro environment"

	try:
		layer_cim = layer.getDefinition("V3")

		popup_ns = getattr(cim_module, "CIMPopup", None)
		if (
			popup_ns is not None
			and hasattr(popup_ns, "CIMTableMediaInfo")
			and hasattr(popup_ns, "CIMPopupInfo")
		):
			table_media = popup_ns.CIMTableMediaInfo()
			popup_info = popup_ns.CIMPopupInfo()
		else:
			table_media = cim_module.CreateCIMObjectFromClassName("CIMTableMediaInfo", "V3")
			popup_info = cim_module.CreateCIMObjectFromClassName("CIMPopupInfo", "V3")

		table_media.fields = popup_fields
		popup_info.mediaInfos = [table_media]

		current_popup = getattr(layer_cim, "popupInfo", None)
		current_media = (
			getattr(current_popup, "mediaInfos", None)
			if current_popup is not None
			else None
		)
		current_fields = None
		if isinstance(current_media, list) and current_media:
			current_fields = getattr(current_media[0], "fields", None)

		if isinstance(current_fields, list) and [str(field) for field in current_fields] == popup_fields:
			return True, False, f"Configured {len(popup_fields)} popup field(s)"

		layer_cim.popupInfo = popup_info
		layer.setDefinition(layer_cim)
		return False, True, f"Configured {len(popup_fields)} popup field(s)"
	except Exception as exc:
		return None, False, f"Could not set popupInfo from cols: {exc}"



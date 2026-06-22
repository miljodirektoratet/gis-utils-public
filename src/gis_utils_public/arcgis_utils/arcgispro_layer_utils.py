"""ArcGIS Pro layer-related helper functions.

Public functions:
- construct_sde_dataset_path: Build dataset path candidates from layer config.
- add_layer_from_sde: Add one layer from SDE source.
- add_sde_layers_and_tables_from_yml_to_map: Add YAML-configured layers/tables from SDE to map.
- resolve_lyrx_path: Resolve LYRX path for one layer.
- apply_lyrx_to_layer: Apply LYRX transfer to a map layer.
- apply_lyrx_to_map_layers_from_config: Apply LYRX transfer to YAML-defined map layers.
- export_map_layers_to_lyrx: Export full layer definitions to LYRX files.
- export_map_layers_to_lyrx_from_config: Export full layer definitions to LYRX files.
- set_cim_feature_table_field_descriptions_from_sde: Rebuild CIM featureTable.fieldDescriptions from SDE source.
- order_cim_feature_table_field_descriptions_by_yml: Order fields using config-first ordering.
- set_cim_feature_table_field_descriptions_visibility_by_yml: Set field visibility from configured field list.
- set_cim_layer_definition_visibility: Set CIM layer/table visibility from config.
- set_cim_layer_definition_service_id: Check and update service layer id.
- set_cim_feature_table_display_field: Configure display field from layer config.
- set_cim_popup_info_fields_by_yml: Configure popup fields from visible config.
"""

import logging
import os
import re
from typing import Any

from .field_utils import (
	generate_field_alias,
	normalize_field_name,
)
from .yaml_config_arcgis import (
	iter_map_service_layer_entries,
	resolve_layer_sde_connection_path,
)

LOGGER = logging.getLogger(__name__)


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


def _get_existing_map_layer_names(map_obj: Any) -> set[str]:
	"""Return case-insensitive set of existing layer and table names in map.

	:param map_obj: ArcGIS Pro map object.
	:return: Set of existing layer/table names normalized with ``casefold()``.
	"""
	existing_names: set[str] = set()
	for layer in map_obj.listLayers():
		layer_name = getattr(layer, "name", None)
		if isinstance(layer_name, str) and layer_name.strip():
			existing_names.add(layer_name.strip().casefold())
	for table in map_obj.listTables():
		table_name = getattr(table, "name", None)
		if isinstance(table_name, str) and table_name.strip():
			existing_names.add(table_name.strip().casefold())
	return existing_names


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


def add_sde_layers_and_tables_from_yml_to_map(
	map_obj: Any,
	service_def_config: dict[str, Any],
	infrastructure_config: dict[str, Any] | None = None,
	env: str = "test",
	access_mode: str = "read",
	fallback_sde_path: str | None = None,
) -> dict[str, Any]:
	"""Add all YAML-defined layers/tables from SDE to the target map.

	:param map_obj: ArcGIS Pro map object.
	:param service_def_config: Full map service definition config dictionary.
	:param infrastructure_config: Optional infrastructure config dictionary.
	:param env: Environment key for resolving map-level SDE connection.
	:param access_mode: Access mode for infrastructure SDE resolution.
	:param fallback_sde_path: Optional fallback SDE path.
	:return: Summary dictionary with per-layer results.
	"""
	layer_entries = iter_map_service_layer_entries(service_def_config)
	results: list[dict[str, Any]] = []
	existing_layer_names = _get_existing_map_layer_names(map_obj)

	LOGGER.debug("Add layers/tables from SDE in config order")

	for layer_name, layer_config in layer_entries:
		normalized_layer_name = layer_name.strip().casefold()
		if normalized_layer_name in existing_layer_names:
			layer_result = _create_add_layer_from_sde_result(
				layer_name=layer_name,
				sde_connection_path=None,
			)
			layer_result["skipped"] = True
			LOGGER.debug("-> Skip adding layer '%s': layer already exists in map", layer_name)
			results.append(layer_result)
			continue

		LOGGER.debug("-> Add layer from SDE source: %s", layer_name)
		try:
			sde_connection_path = resolve_layer_sde_connection_path(
				service_def_config=service_def_config,
				layer_config=layer_config,
				infrastructure_config=infrastructure_config,
				env=env,
				access_mode=access_mode,
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
			LOGGER.debug("-> Added layer '%s' from %s", layer_name, layer_result.get("dataset_path"))
		elif layer_result.get("skipped"):
			LOGGER.debug("-> Skipped layer '%s'", layer_name)
		else:
			LOGGER.warning("-> Failed adding layer '%s': %s", layer_name, layer_result.get("error"))
		results.append(layer_result)

	added_count = sum(1 for result in results if bool(result.get("added")))
	skipped_count = sum(1 for result in results if bool(result.get("skipped")))
	LOGGER.debug(
		"-> Added %d/%d layer/table entry(ies) to map (skipped existing: %d)",
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

		# Prefix match: file ends with _{layer_name}.lyrx (e.g. vern_0_naturvern_omraade.lyrx)
		prefix_suffix = f"_{normalized_name}.lyrx"
		prefix_matches = sorted(
			[
				paths[0]
				for file_name, paths in lyrx_lookup_index.items()
				if file_name.endswith(prefix_suffix)
			],
			key=lambda item: item.lower(),
		)
		if prefix_matches:
			selected = prefix_matches[0]
			if len(prefix_matches) > 1:
				LOGGER.warning(
					"-> Multiple prefix LYRX matches for '%s'. Using first alphabetically: %s",
					layer_name,
					selected,
				)
			result.update(
				{
					"lyrx_path": selected,
					"match_type": "prefix",
					"candidate_count": len(prefix_matches),
					"candidate_paths": prefix_matches,
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

	LOGGER.debug(
		"Apply LYRX transfer to map layers (mode=%s, allow_suffix_match=%s, recurse_subfolders=%s)",
		transfer_mode,
		allow_suffix_match,
		recurse_subfolders,
	)
	all_lyrx_files = _iter_lyrx_file_paths(lyrx_dir, recurse_subfolders)
	lyrx_lookup_index = _build_lyrx_lookup_index(all_lyrx_files)

	for layer_name, layer_config in layer_entries:
		if isinstance(layer_config, dict) and layer_config.get("type") == "table":
			LOGGER.debug("-> Skip LYRX transfer for table '%s'", layer_name)
			continue

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
			LOGGER.debug(
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


def export_map_layers_to_lyrx(
	map_obj: Any,
	lyrx_dir: str,
	layer_names: list[str] | None = None,
	file_prefix: str | None = None,
	file_suffix: str | None = None,
	layer_ids: dict[str, Any] | None = None,
	overwrite: bool = True,
) -> dict[str, Any]:
	"""Export full map-layer definitions to LYRX files.

	When ``layer_names`` is provided, export only those names in given order.
	When omitted, export all non-group, non-basemap layers in the map.

	Filename pattern:
	- When ``file_prefix`` and ``layer_ids`` are both set:
	  ``<file_prefix>_<service_id>_<normalized_layer_name>.lyrx``.
	- When only ``file_prefix`` is set: ``<file_prefix>_<normalized_layer_name>.lyrx``.
	- Otherwise: ``<layer_name>_<file_suffix>.lyrx``.

	:param map_obj: ArcGIS Pro map object.
	:param lyrx_dir: Target LYRX directory.
	:param layer_names: Optional ordered list of target layer names.
	:param file_prefix: Optional filename prefix (e.g. data product name).
		When set, ``file_suffix`` is ignored.
	:param file_suffix: Optional LYRX filename suffix appended as ``<name>_<suffix>.lyrx``.
		Ignored when ``file_prefix`` is set.
	:param layer_ids: Optional mapping of layer name to service ID integer.
		Only used when ``file_prefix`` is set. Layers missing from this dict
		are exported without the id segment.
	:param overwrite: Whether to overwrite existing LYRX files.
	:return: Summary dictionary with per-layer export results.
	"""
	if not isinstance(lyrx_dir, str) or not lyrx_dir.strip():
		raise ValueError("LYRX directory must be a non-empty string")

	resolved_lyrx_dir = os.path.abspath(lyrx_dir)
	os.makedirs(resolved_lyrx_dir, exist_ok=True)

	suffix = str(file_suffix or "").strip()
	prefix = str(file_prefix or "").strip() or None
	results: list[dict[str, Any]] = []

	def _is_exportable_layer(layer_obj: Any) -> bool:
		return not bool(getattr(layer_obj, "isGroupLayer", False)) and not bool(
			getattr(layer_obj, "isBasemapLayer", False)
		)

	def _iter_leaf_layers(layer_collection: list[Any]) -> list[Any]:
		collected: list[Any] = []
		for layer_obj in layer_collection:
			if bool(getattr(layer_obj, "isGroupLayer", False)):
				try:
					collected.extend(_iter_leaf_layers(layer_obj.listLayers()))
				except Exception:
					continue
				continue
			collected.append(layer_obj)
		return collected

	def _append_result(
		layer_name: str,
		lyrx_path: str | None,
		exported: bool,
		skipped: bool,
		error: str | None,
		reason: str,
	) -> None:
		results.append(
			{
				"layer_name": layer_name,
				"lyrx_path": lyrx_path,
				"exported": exported,
				"skipped": skipped,
				"error": error,
				"reason": reason,
			}
		)

	def _export_one(layer_name: str, target_layer: Any) -> None:
		if not _is_exportable_layer(target_layer):
			_append_result(layer_name, None, False, True, None, "non_exportable_layer")
			return

		if prefix:
			layer_stem = re.sub(r"[^0-9a-z_]+", "_", layer_name.lower()).strip("_") or "layer"
			if layer_ids is not None and layer_name in layer_ids:
				layer_id = layer_ids[layer_name]
				lyrx_filename = f"{prefix}_{layer_id}_{layer_stem}.lyrx"
			else:
				lyrx_filename = f"{prefix}_{layer_stem}.lyrx"
		else:
			file_stem = layer_name.replace("/", "_").replace("\\", "_")
			lyrx_filename = f"{file_stem}_{suffix}.lyrx" if suffix else f"{file_stem}.lyrx"
		lyrx_path = os.path.join(resolved_lyrx_dir, lyrx_filename)
		try:
			if overwrite and os.path.exists(lyrx_path):
				os.remove(lyrx_path)
			target_layer.saveACopy(lyrx_path)
			_append_result(layer_name, lyrx_path, True, False, None, "exported")
		except Exception as exc:
			_append_result(layer_name, lyrx_path, False, False, str(exc), "export_failed")

	LOGGER.debug(
		"Export map layers to LYRX (lyrx_dir=%s, suffix=%s, overwrite=%s)",
		resolved_lyrx_dir,
		suffix,
		overwrite,
	)

	if isinstance(layer_names, list):
		target_name_sequence = [
			str(name).strip() for name in layer_names if isinstance(name, str) and name.strip()
		]
		for layer_name in target_name_sequence:
			target_layers = map_obj.listLayers(layer_name)
			if not target_layers:
				_append_result(
					layer_name,
					None,
					False,
					False,
					"Target map layer was not found",
					"missing_layer",
				)
				continue
			if len(target_layers) > 1:
				LOGGER.warning(
					"-> Multiple target map layers found for '%s'. Using first match.",
					layer_name,
				)
			_export_one(layer_name, target_layers[0])
	else:
		for target_layer in _iter_leaf_layers(map_obj.listLayers()):
			layer_name = str(getattr(target_layer, "name", "") or "").strip()
			if not layer_name:
				continue
			_export_one(layer_name, target_layer)

	exported_count = sum(1 for item in results if bool(item.get("exported")))
	skipped_count = sum(1 for item in results if bool(item.get("skipped")))
	error_count = sum(1 for item in results if bool(item.get("error")))

	return {
		"layer_results": results,
		"layer_total": len(results),
		"layers_exported_count": exported_count,
		"layers_skipped_count": skipped_count,
		"layers_error_count": error_count,
		"lyrx_dir": resolved_lyrx_dir,
		"file_suffix": suffix,
		"overwrite": overwrite,
	}


def export_map_layers_to_lyrx_from_config(
	map_obj: Any,
	service_def_config: dict[str, Any],
	lyrx_dir: str,
	file_prefix: str | None = None,
	file_suffix: str | None = None,
	overwrite: bool = True,
) -> dict[str, Any]:
	"""Export full map-layer definitions to LYRX files from YAML layer order.

	Only feature layers are exported. Table entries (``type: table``) are skipped.

	Filename pattern:
	- When ``file_prefix`` is set: ``<file_prefix>_<service_id>_<normalized_layer_name>.lyrx``.
	- Otherwise: ``<layer_name>_<file_suffix>.lyrx``.

	:param map_obj: ArcGIS Pro map object.
	:param service_def_config: Full map service definition config dictionary.
	:param lyrx_dir: Target LYRX directory.
	:param file_prefix: Optional filename prefix (e.g. data product name).
		When set, ``file_suffix`` is ignored and ``service_id`` from config is
		included in the filename.
	:param file_suffix: Optional LYRX filename suffix. Ignored when ``file_prefix`` is set.
	:param overwrite: Whether to overwrite existing LYRX files.
	:return: Summary dictionary with per-layer export results.
	"""
	layer_entries = iter_map_service_layer_entries(service_def_config)
	layer_names = []
	layer_ids: dict[str, Any] = {}
	for layer_name, layer_config in layer_entries:
		if isinstance(layer_config, dict) and layer_config.get("type") == "table":
			continue
		layer_names.append(layer_name)
		if isinstance(layer_config, dict) and layer_config.get("service_id") is not None:
			layer_ids[layer_name] = layer_config["service_id"]

	summary = export_map_layers_to_lyrx(
		map_obj=map_obj,
		lyrx_dir=lyrx_dir,
		layer_names=layer_names,
		file_prefix=file_prefix,
		file_suffix=file_suffix,
		layer_ids=layer_ids if layer_ids else None,
		overwrite=overwrite,
	)
	summary["layer_total"] = len(layer_entries)
	summary["layers_skipped_count"] = int(summary.get("layers_skipped_count", 0)) + (
		len(layer_entries) - len(layer_names)
	)
	return summary


def _get_layer_fields_and_descriptions(layer: Any) -> tuple[Any, Any, Any]:
	"""Return layer fields, CIM definition, and feature-table field descriptions.

	Field sources are probed in priority/fallback order (dataSource, Describe,
	layer object), and the richest field set is selected to reduce risk of using
	trimmed views.

	:param layer: ArcGIS layer object.
	:return: Tuple ``(fields, cim, field_descriptions)`` or ``(None, None, None)``
		when fields/CIM cannot be resolved.
	"""
	import arcpy

	if getattr(layer, "isGroupLayer", False) or getattr(layer, "isBasemapLayer", False):
		return None, None, None

	candidates: list[list[Any]] = []

	# Preferred: datasource path on layer.
	try:
		data_source = getattr(layer, "dataSource", None)
		if isinstance(data_source, str) and data_source.strip():
			fields_from_datasource = arcpy.ListFields(data_source)
			if fields_from_datasource:
				candidates.append(list(fields_from_datasource))
	except Exception:
		pass

	# Fallback: describe metadata (often exposes full source fields).
	try:
		desc = arcpy.Describe(layer)
		desc_fields = getattr(desc, "fields", None)
		if desc_fields:
			candidates.append(list(desc_fields))

		catalog_path = getattr(desc, "catalogPath", None)
		if isinstance(catalog_path, str) and catalog_path.strip():
			fields_from_catalog = arcpy.ListFields(catalog_path)
			if fields_from_catalog:
				candidates.append(list(fields_from_catalog))
	except Exception:
		pass

	# Last resort: layer-scoped fields (can reflect trimmed/view state).
	try:
		fields_from_layer = arcpy.ListFields(layer)
		if fields_from_layer:
			candidates.append(list(fields_from_layer))
	except Exception:
		pass

	if not candidates:
		return None, None, None

	# Prefer the richest candidate set to avoid propagating trimmed field sets.
	fields = max(candidates, key=len)

	try:
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

	candidates: list[list[Any]] = []
	errors: list[str] = []

	try:
		data_source = getattr(layer, "dataSource", None)
		if isinstance(data_source, str) and data_source.strip():
			fields_from_datasource = arcpy.ListFields(data_source)
			if fields_from_datasource:
				candidates.append(list(fields_from_datasource))
	except Exception as exc:
		errors.append(f"dataSource: {exc}")

	try:
		desc = arcpy.Describe(layer)
		desc_fields = getattr(desc, "fields", None)
		if desc_fields:
			candidates.append(list(desc_fields))

		catalog_path = getattr(desc, "catalogPath", None)
		if isinstance(catalog_path, str) and catalog_path.strip():
			fields_from_catalog = arcpy.ListFields(catalog_path)
			if fields_from_catalog:
				candidates.append(list(fields_from_catalog))
	except Exception as exc:
		errors.append(f"describe: {exc}")

	try:
		fields_from_layer = arcpy.ListFields(layer)
		if fields_from_layer:
			candidates.append(list(fields_from_layer))
	except Exception as exc:
		errors.append(f"layer: {exc}")

	if not candidates:
		return {}, "Could not list fields: " + "; ".join(errors)

	fields = max(candidates, key=len)

	lookup: dict[str, str] = {}
	for field in fields:
		actual_name = getattr(field, "name", None)
		if not isinstance(actual_name, str):
			continue
		normalized = normalize_field_name(actual_name)
		if normalized and normalized not in lookup:
			lookup[normalized] = actual_name

	return lookup, None


def get_field_names_from_yml(layer: Any, configured_cols: Any) -> tuple[list[str], str]:
	"""Resolve configured cols to an explicit field-name list.

	Supports the special keyword ``all`` (or ``*``) to include all source
	fields on the layer.

	:param layer: ArcGIS layer object.
	:param configured_cols: Raw ``cols`` value from config.
	:return: Tuple ``(resolved_cols, cols_mode)``.
	"""
	layer_name = getattr(layer, "name", "<unknown>")

	if isinstance(configured_cols, list):
		resolved = [field_name for field_name in configured_cols if isinstance(field_name, str) and field_name.strip()]
		return resolved, "list"

	if isinstance(configured_cols, str):
		normalized_token = configured_cols.strip().lower()
		if normalized_token in {"all", "*"}:
			lookup, error_message = _get_layer_field_name_lookup(layer)
			if error_message:
				LOGGER.warning(
					"get_field_names_from_yml: could not resolve all fields for '%s': %s",
					layer_name,
					error_message,
				)
				return [], "all_lookup_failed"
			return list(lookup.values()), "all"

		LOGGER.warning(
			"get_field_names_from_yml: invalid cols string for '%s': %s",
			layer_name,
			configured_cols,
		)
		return [], "invalid_string"

	if configured_cols is None:
		return [], "none"

	LOGGER.warning(
		"get_field_names_from_yml: invalid cols type for '%s': %s",
		layer_name,
		type(configured_cols).__name__,
	)
	return [], "invalid_type"


def order_cim_feature_table_field_descriptions_by_yml(layer: Any, desired_field_order: list[str]) -> int | None:
	"""Reorder CIM feature-table field descriptions by YAML order.

	Updates CIM object ``CIMVectorLayer.featureTable.fieldDescriptions``.
	Spec: https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMVectorLayers.md#cimfeaturetable

	:param layer: ArcGIS layer object.
	:param desired_field_order: Desired field order from config.
	:return: Reordered field count, 0 if unchanged, or None when unavailable.
	"""
	layer_name = getattr(layer, "name", "<unknown>")
	if not desired_field_order:
		LOGGER.debug("order_cim_feature_table_field_descriptions_by_yml: skip '%s' (no cols configured)", layer_name)
		return 0

	_, cim, field_descriptions = _get_layer_fields_and_descriptions(layer)
	if not field_descriptions:
		LOGGER.debug("order_cim_feature_table_field_descriptions_by_yml: skip '%s' (no field descriptions)", layer_name)
		return None

	field_by_name: dict[str, Any] = {}
	for field_description in field_descriptions:
		raw_name = getattr(field_description, "fieldName", None) or getattr(
			field_description, "name", None
		)
		normalized = normalize_field_name(raw_name)
		if normalized and normalized not in field_by_name:
			field_by_name[normalized] = field_description

	reordered_descriptions = []
	seen_fields: set[str] = set()

	for field_name in desired_field_order:
		normalized = normalize_field_name(field_name)
		if normalized in field_by_name:
			reordered_descriptions.append(field_by_name[normalized])
			seen_fields.add(normalized)

	remaining_descriptions = []
	for field_description in field_descriptions:
		raw_name = getattr(field_description, "fieldName", None) or getattr(
			field_description, "name", None
		)
		normalized = normalize_field_name(raw_name)
		if normalized not in seen_fields:
			remaining_descriptions.append(field_description)

	remaining_descriptions.sort(
		key=lambda field_description: (
			(getattr(field_description, "fieldName", None) or getattr(field_description, "name", "")).lower()
		)
	)
	reordered_descriptions.extend(remaining_descriptions)

	if reordered_descriptions == field_descriptions:
		LOGGER.debug("order_cim_feature_table_field_descriptions_by_yml: already ordered for '%s'", layer_name)
		return 0

	cim.featureTable.fieldDescriptions = reordered_descriptions
	layer.setDefinition(cim)
	LOGGER.debug(
		"order_cim_feature_table_field_descriptions_by_yml: updated '%s' (field_count=%s)",
		layer_name,
		len(reordered_descriptions),
	)
	return len(reordered_descriptions)


def set_cim_feature_table_field_descriptions_from_sde(layer: Any) -> tuple[int, int]:
	"""Rebuild CIM feature-table field descriptions from SDE source metadata.

	Updates CIM object ``CIMVectorLayer.featureTable.fieldDescriptions`` and
	its ``fieldDescriptions[].alias``, ``fieldDescriptions[].fieldAlias``, and
	``fieldDescriptions[].visible`` values.

	Alias behavior:
	- Preferred source: SDE field alias (``aliasName``/``alias``).
	- Fallback when missing: generated alias via ``generate_field_alias``.

	The function writes both ``alias`` and ``fieldAlias`` to keep ArcGIS Pro
	property variants aligned.
	Spec: https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMVectorLayers.md#cimfeaturetable

	:param layer: ArcGIS layer object.
	:return: Tuple ``(rebuilt_count, total_fields)`` where both values reflect
		the rebuilt feature-table field-description count.
	"""
	layer_name = getattr(layer, "name", "<unknown>")
	fields, cim, field_descriptions = _get_layer_fields_and_descriptions(layer)
	if fields is None or cim is None:
		LOGGER.debug("set_cim_feature_table_field_descriptions_from_sde: skip '%s' (no fields available)", layer_name)
		return 0, 0

	feature_table = getattr(cim, "featureTable", None)
	if feature_table is None:
		LOGGER.debug("set_cim_feature_table_field_descriptions_from_sde: skip '%s' (no featureTable on CIM)", layer_name)
		return 0, 0

	try:
		import arcpy
	except Exception:
		arcpy = None

	cim_module = getattr(arcpy, "cim", None) if arcpy is not None else None
	builder = getattr(cim, "_arc_object", None)

	current_descriptions = list(field_descriptions or [])

	original_description_snapshot = [
		{
			"fieldName": getattr(fd, "fieldName", None) or getattr(fd, "name", None),
			"alias": getattr(fd, "alias", None) or getattr(fd, "fieldAlias", None),
		}
		for fd in current_descriptions
	]

	# Always rebuild from datasource to ensure all SDE fields are present.
	rebuilt: list[Any] = []
	for field in fields:
		field_name = field.get("name") if isinstance(field, dict) else getattr(field, "name", None)
		if not isinstance(field_name, str) or not field_name:
			continue
		# Source of truth for alias should be SDE field alias.
		field_alias = (
			field.get("alias") if isinstance(field, dict) else getattr(field, "aliasName", None)
		)
		if isinstance(field_alias, str) and field_alias.strip():
			LOGGER.debug(
				"set_cim_feature_table_field_descriptions_from_sde: read alias from SDE for layer '%s' field '%s': '%s'",
				layer_name,
				field_name,
				field_alias,
			)
		else:
			field_alias = generate_field_alias(field_name)
			LOGGER.warning(
				"set_cim_feature_table_field_descriptions_from_sde: missing SDE alias for layer '%s' field '%s'; regenerated alias '%s'",
				layer_name,
				field_name,
				field_alias,
			)

		fd = None
		if cim_module is not None:
			create_fn = getattr(cim_module, "CreateCIMObjectFromClassName", None)
			if callable(create_fn):
				try:
					fd = create_fn("CIMFieldDescription", "V3")
				except Exception:
					fd = None
		if fd is None and builder is not None:
			try:
				fd = builder.createObject("CIMFieldDescription")
			except Exception:
				fd = None
		if fd is None:
			continue

		setattr(fd, "fieldName", field_name)
		setattr(fd, "alias", field_alias)
		# Keep both properties aligned since ArcGIS may expose either alias or fieldAlias.
		setattr(fd, "fieldAlias", field_alias)
		setattr(fd, "visible", True)
		rebuilt.append(fd)

	if not rebuilt:
		LOGGER.debug("set_cim_feature_table_field_descriptions_from_sde: skip '%s' (could not build field descriptions)", layer_name)
		return 0, 0

	rebuilt_description_snapshot = [
		{
			"fieldName": getattr(fd, "fieldName", None) or getattr(fd, "name", None),
			"alias": getattr(fd, "alias", None) or getattr(fd, "fieldAlias", None),
		}
		for fd in rebuilt
	]
	LOGGER.debug(
		"set_cim_feature_table_field_descriptions_from_sde: '%s' CIM fieldDescriptions original -> updated\noriginal=%s\nupdated=%s",
		layer_name,
		original_description_snapshot,
		rebuilt_description_snapshot,
	)

	feature_table.fieldDescriptions = rebuilt
	layer.setDefinition(cim)
	LOGGER.debug(
		"set_cim_feature_table_field_descriptions_from_sde: rebuilt '%s' from SDE datasource (count=%s, was=%s)",
		layer_name,
		len(rebuilt),
		len(current_descriptions),
	)
	return len(rebuilt), len(rebuilt)


def set_cim_feature_table_field_descriptions_visibility_by_yml(
	layer: Any,
	visible_field_names: list[str],
) -> tuple[int, int, int, int, int, list[str]]:
	"""Set CIM field-description visibility from YAML field list.

	Updates CIM object ``CIMVectorLayer.featureTable.fieldDescriptions[].visible``.
	Spec: https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMVectorLayers.md#cimfeaturetable

	:param layer: ArcGIS layer object.
	:param visible_field_names: Configured visible field list.
	:return: Visibility summary tuple.
	"""
	layer_name = getattr(layer, "name", "<unknown>")
	if not visible_field_names:
		LOGGER.debug("set_cim_feature_table_field_descriptions_visibility_by_yml: skip '%s' (no cols configured)", layer_name)
		return 0, 0, 0, 0, 0, []

	_, cim, field_descriptions = _get_layer_fields_and_descriptions(layer)
	if field_descriptions is None:
		LOGGER.debug("set_cim_feature_table_field_descriptions_visibility_by_yml: skip '%s' (no field descriptions)", layer_name)
		return 0, 0, 0, 0, 0, []

	visible_set = {
		normalized
		for normalized in (normalize_field_name(name) for name in visible_field_names)
		if normalized
	}

	made_visible = 0
	made_hidden = 0

	for field_description in field_descriptions:
		raw_name = getattr(field_description, "fieldName", None) or getattr(
			field_description, "name", None
		)
		normalized = normalize_field_name(raw_name)
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
		normalized = normalize_field_name(raw_name)
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
		if normalize_field_name(name) not in available_names
	]
	LOGGER.debug(
		"set_cim_feature_table_field_descriptions_visibility_by_yml: updated '%s' (made_visible=%s, made_hidden=%s, target_visible=%s, missing=%s)",
		layer_name,
		made_visible,
		made_hidden,
		target_visible,
		len(missing_config_fields),
	)

	return (
		made_visible,
		made_hidden,
		final_visible,
		final_hidden,
		target_visible,
		missing_config_fields,
	)


def set_cim_layer_definition_visibility(
	item: Any,
	expected_visible: Any,
) -> tuple[Any, bool, str]:
	"""Set CIM layer/table visibility from configuration.

	Updates the ``visibility`` attribute in CIMLayerDefinition for layers and
	CIMStandaloneTable for tables. Applies configuration value and reports
	whether visibility matches expected state.

	:param item: ArcGIS map layer or table object.
	:param expected_visible: Expected visibility (typically bool).
	:return: Tuple ``(is_correct, was_updated, info_message)``.
	"""
	item_name = getattr(item, "name", "<unknown>")
	if expected_visible is None:
		LOGGER.debug("set_cim_layer_definition_visibility: skip '%s' (no visible configured)", item_name)
		return None, False, "No visible configured"

	if not isinstance(expected_visible, bool):
		LOGGER.debug("set_cim_layer_definition_visibility: skip '%s' (invalid visible value)", item_name)
		return None, False, "Configured visible must be true/false"

	try:
		import arcpy
		item_cim = item.getDefinition("V3")
		current_visible = bool(getattr(item_cim, "visibility", False))
		if current_visible == expected_visible:
			LOGGER.debug("set_cim_layer_definition_visibility: '%s' visibility=%s (no change needed)", item_name, current_visible)
			return True, False, f"visibility={current_visible}"

		setattr(item_cim, "visibility", expected_visible)
		item.setDefinition(item_cim)
		LOGGER.debug("set_cim_layer_definition_visibility: '%s' visibility=%s (updated)", item_name, expected_visible)
		return False, True, f"visibility={expected_visible}"
	except Exception as exc:
		LOGGER.warning("set_cim_layer_definition_visibility: failed for '%s': %s", item_name, exc)
		return None, False, f"Could not set visibility: {exc}"


def check_and_update_definition_query(
	item: Any,
	expected_query: Any,
) -> tuple[Any, bool, str]:
	"""Check map item definition query and update when needed.

	Supports feature layers and standalone tables. Uses direct
	``definitionQuery`` property when available, then falls back to CIM
	``definitionExpression`` when possible.

	:param item: ArcGIS map item object (layer or table).
	:param expected_query: Configured SQL where-clause string.
	:return: Tuple ``(is_correct, was_updated, info_message)``.
	"""
	item_name = getattr(item, "name", "<unknown>")
	if expected_query is None:
		LOGGER.debug("check_and_update_definition_query: skip '%s' (no definition_query configured)", item_name)
		return None, False, "No definition_query configured"

	if not isinstance(expected_query, str):
		LOGGER.debug("check_and_update_definition_query: skip '%s' (invalid definition_query)", item_name)
		return None, False, "Configured definition_query must be a string"

	desired_query = expected_query.strip()

	# Preferred path: direct ArcPy property.
	if hasattr(item, "definitionQuery"):
		try:
			current_query_raw = getattr(item, "definitionQuery", "")
			current_query = current_query_raw.strip() if isinstance(current_query_raw, str) else ""
			if current_query == desired_query:
				return True, False, current_query
			setattr(item, "definitionQuery", desired_query)
			return False, True, desired_query
		except Exception as exc:
			LOGGER.debug(
				"check_and_update_definition_query: direct property failed for '%s': %s",
				item_name,
				exc,
			)

	# Fallback: CIM attribute update.
	try:
		item_cim = item.getDefinition("V3")
		for attr_name in ("definitionExpression", "definitionQuery"):
			if not hasattr(item_cim, attr_name):
				continue

			current_query_raw = getattr(item_cim, attr_name, "")
			current_query = current_query_raw.strip() if isinstance(current_query_raw, str) else ""
			if current_query == desired_query:
				return True, False, current_query

			setattr(item_cim, attr_name, desired_query)
			item.setDefinition(item_cim)
			return False, True, desired_query

		return None, False, "Definition query property is not available for this item"
	except Exception as exc:
		LOGGER.warning("check_and_update_definition_query: failed for '%s': %s", item_name, exc)
		return None, False, f"Could not set definition query: {exc}"


def set_cim_layer_definition_service_id(layer: Any, expected_service_id: Any) -> tuple[bool, bool]:
	"""Set CIM service id for a layer or standalone table.

	Updates CIM object ``CIMLayerDefinition.serviceLayerID`` for layers and
	``CIMStandaloneTable.serviceTableID`` for standalone tables.
	Specs:
	- https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMVectorLayers.md#cimlayerdefinition-8
	- https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMStandaloneTable.md

	Supported CIM attributes (in lookup order):
	- ``serviceLayerID``
	- ``serviceTableID``

	:param layer: ArcGIS map item (feature layer or standalone table).
	:param expected_service_id: Value from YAML ``service_id``.
	:return: Tuple ``(is_correct, was_updated)``.
	"""
	layer_name = getattr(layer, "name", "<unknown>")
	if expected_service_id is None:
		LOGGER.debug("set_cim_layer_definition_service_id: skip '%s' (no service_id configured)", layer_name)
		return True, False

	try:
		expected_id = int(expected_service_id)
	except Exception:
		LOGGER.warning(
			"set_cim_layer_definition_service_id: skip '%s' (invalid configured service_id: %r)",
			layer_name,
			expected_service_id,
		)
		return False, False

	try:
		layer_cim = layer.getDefinition("V3")

		if hasattr(layer_cim, "serviceLayerID"):
			target_attr = "serviceLayerID"
		elif hasattr(layer_cim, "serviceTableID"):
			target_attr = "serviceTableID"
		else:
			LOGGER.warning(
				"set_cim_layer_definition_service_id: failed for '%s': missing canonical CIM field "
				"('serviceLayerID' or 'serviceTableID')",
				layer_name,
			)
			return False, False

		attr_value = getattr(layer_cim, target_attr, None)
		try:
			current_id = int(attr_value) if attr_value is not None else None
		except Exception:
			current_id = None

		if current_id == expected_id:
			LOGGER.debug("set_cim_layer_definition_service_id: already correct for '%s' (%s)", layer_name, current_id)
			return True, False

		setattr(layer_cim, target_attr, expected_id)
		layer.setDefinition(layer_cim)
		LOGGER.debug(
			"set_cim_layer_definition_service_id: updated '%s' (%s -> %s) via %s",
			layer_name,
			current_id,
			expected_id,
			target_attr,
		)
		return False, True
	except Exception as exc:
		LOGGER.warning("set_cim_layer_definition_service_id: failed for '%s': %s", layer_name, exc)
		return False, False


def set_cim_feature_table_display_field(
	layer: Any,
	display_field_name: Any,
) -> tuple[Any, bool, str]:
	"""Set CIM display field when configured field exists on layer.

	Updates CIM object ``CIMVectorLayer.featureTable.displayField``.
	Spec: https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMVectorLayers.md#cimfeaturetable

	:param layer: ArcGIS layer object.
	:param display_field_name: Configured display field.
	:return: Tuple ``(is_correct, was_updated, info_message)``.
	"""
	layer_name = getattr(layer, "name", "<unknown>")
	if not isinstance(display_field_name, str) or not display_field_name.strip():
		LOGGER.debug("set_cim_feature_table_display_field: skip '%s' (no display_field configured)", layer_name)
		return None, False, "No display_field configured"

	requested = display_field_name.strip()
	requested_normalized = normalize_field_name(requested)
	if requested_normalized is None:
		LOGGER.debug("set_cim_feature_table_display_field: skip '%s' (empty display_field)", layer_name)
		return None, False, "Configured display_field is empty after normalization"

	available_by_normalized, error_message = _get_layer_field_name_lookup(layer)
	if error_message:
		LOGGER.warning("set_cim_feature_table_display_field: field lookup failed for '%s': %s", layer_name, error_message)
		return None, False, error_message

	if requested_normalized not in available_by_normalized:
		LOGGER.debug(
			"set_cim_feature_table_display_field: requested field not found for '%s' (requested=%s)",
			layer_name,
			requested,
		)
		return None, False, f"Configured display_field '{requested}' not found in layer fields"

	resolved_field_name = available_by_normalized[requested_normalized]

	try:
		layer_cim = layer.getDefinition("V3")
		feature_table = getattr(layer_cim, "featureTable", None)
		if feature_table is None:
			return None, False, "Layer CIM does not expose featureTable"

		current_display = getattr(feature_table, "displayField", None)
		if normalize_field_name(current_display) == requested_normalized:
			LOGGER.debug(
				"set_cim_feature_table_display_field: already correct for '%s' (%s)",
				layer_name,
				resolved_field_name,
			)
			return True, False, resolved_field_name

		setattr(feature_table, "displayField", resolved_field_name)
		layer.setDefinition(layer_cim)
		LOGGER.debug(
			"set_cim_feature_table_display_field: updated '%s' (%s)",
			layer_name,
			resolved_field_name,
		)
		return False, True, resolved_field_name
	except Exception as exc:
		LOGGER.warning("set_cim_feature_table_display_field: failed for '%s': %s", layer_name, exc)
		return None, False, f"Could not set display field: {exc}"


def set_cim_popup_info_fields_by_yml(
	layer: Any,
	visible_field_names: list[str],
) -> tuple[Any, bool, str]:
	"""Set popup field ordering from YAML ``cols`` into layer CIM popup structures.

	This function writes popup ordering to both relevant CIM popup paths:
	- ``CIMPopupInfo.mediaInfos[].fields`` (table media field sequence)
	- ``CIMPopupInfo.fieldDescriptions`` (``CIMPopupFieldDescription`` sequence)

	Ordering behavior:
	- Start from configured ``visible_field_names`` (typically YAML ``cols``).
	- Resolve to actual layer field names and remove duplicates.
	- Mirror order from ``featureTable.fieldDescriptions`` for matching fields.
	- Append any configured fields missing from ``featureTable.fieldDescriptions``.

	Alias behavior:
	- ``CIMPopupFieldDescription.alias`` is copied from corresponding
	  ``featureTable.fieldDescriptions`` (``alias``/``fieldAlias``) when available.
	- ``mediaInfos[].useLayerFields`` is set to ``False`` to enforce explicit
	  field sequencing.

	Spec references:
	- https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMPopup.md#cimpopupinfo
	- https://github.com/Esri/cim-spec/blob/main/docs/v3/CIMPopup.md#cimpopupfielddescription

	:param layer: ArcGIS layer object.
	:param visible_field_names: Ordered configured field names (YAML ``cols``).
	:return: Tuple ``(is_correct, was_updated, info_message)`` where:
		- ``is_correct`` indicates whether popup order already matched,
		- ``was_updated`` indicates whether CIM was written,
		- ``info_message`` provides a short status summary.
	"""
	import arcpy
	layer_name = getattr(layer, "name", "<unknown>")

	if not isinstance(visible_field_names, list) or not visible_field_names:
		LOGGER.debug("set_cim_popup_info_fields_by_yml: skip '%s' (no cols configured)", layer_name)
		return None, False, "No cols configured"

	normalized_requested: list[str] = []
	seen: set[str] = set()
	for name in visible_field_names:
		normalized = normalize_field_name(name)
		if normalized and normalized not in seen:
			seen.add(normalized)
			normalized_requested.append(normalized)

	if not normalized_requested:
		LOGGER.debug("set_cim_popup_info_fields_by_yml: skip '%s' (no valid cols)", layer_name)
		return None, False, "No valid field names in cols"

	available_by_normalized, error_message = _get_layer_field_name_lookup(layer)
	if error_message:
		LOGGER.warning("set_cim_popup_info_fields_by_yml: field lookup failed for '%s': %s", layer_name, error_message)
		return None, False, error_message

	popup_fields = [
		available_by_normalized[name]
		for name in normalized_requested
		if name in available_by_normalized
	]
	if not popup_fields:
		LOGGER.debug("set_cim_popup_info_fields_by_yml: no fields found for '%s' from configured cols", layer_name)
		return None, False, "No configured cols fields were found in layer"

	cim_module = getattr(arcpy, "cim", None)
	if cim_module is None:
		LOGGER.warning("set_cim_popup_info_fields_by_yml: arcpy.cim missing for '%s'", layer_name)
		return None, False, "arcpy.cim is not available in this ArcGIS Pro environment"

	try:
		layer_cim = layer.getDefinition("V3")
		feature_table = getattr(layer_cim, "featureTable", None)
		feature_descriptions = (
			getattr(feature_table, "fieldDescriptions", None)
			if feature_table is not None
			else None
		)

		# Build popup field sequence from featureTable.fieldDescriptions so popup
		# name/alias/order mirrors layer field metadata as closely as possible.
		requested_normalized_set = {
			normalize_field_name(field_name)
			for field_name in popup_fields
			if normalize_field_name(field_name)
		}
		ordered_popup_fields: list[str] = []
		ordered_popup_alias_by_name: dict[str, str] = {}
		seen_popup_names: set[str] = set()

		if isinstance(feature_descriptions, list):
			for field_description in feature_descriptions:
				raw_name = getattr(field_description, "fieldName", None) or getattr(
					field_description,
					"name",
					None,
				)
				normalized_name = normalize_field_name(raw_name)
				if not normalized_name or normalized_name not in requested_normalized_set:
					continue
				resolved_name = available_by_normalized.get(normalized_name) or raw_name
				if not isinstance(resolved_name, str) or not resolved_name:
					continue
				if resolved_name in seen_popup_names:
					continue

				ordered_popup_fields.append(resolved_name)
				seen_popup_names.add(resolved_name)

				alias_value = getattr(field_description, "alias", None) or getattr(
					field_description,
					"fieldAlias",
					None,
				)
				if isinstance(alias_value, str):
					ordered_popup_alias_by_name[resolved_name] = alias_value

		# Add any configured popup fields missing in feature descriptions.
		for field_name in popup_fields:
			if field_name not in seen_popup_names:
				ordered_popup_fields.append(field_name)
				seen_popup_names.add(field_name)

		popup_ns = getattr(cim_module, "CIMPopup", None)
		popup_field_description_factory: Any = None
		if (
			popup_ns is not None
			and hasattr(popup_ns, "CIMTableMediaInfo")
			and hasattr(popup_ns, "CIMPopupInfo")
		):
			table_media = popup_ns.CIMTableMediaInfo()
			popup_info = getattr(layer_cim, "popupInfo", None) or popup_ns.CIMPopupInfo()
			popup_field_description_factory = (
				popup_ns.CIMPopupFieldDescription
				if hasattr(popup_ns, "CIMPopupFieldDescription")
				else None
			)
		else:
			table_media = cim_module.CreateCIMObjectFromClassName("CIMTableMediaInfo", "V3")
			popup_info = getattr(layer_cim, "popupInfo", None) or cim_module.CreateCIMObjectFromClassName("CIMPopupInfo", "V3")
			popup_field_description_factory = None

		if popup_field_description_factory is None:
			popup_field_description_factory = lambda: cim_module.CreateCIMObjectFromClassName(
				"CIMPopupFieldDescription", "V3"
			)

		table_media.fields = ordered_popup_fields
		table_media.useLayerFields = False
		popup_info.mediaInfos = [table_media]

		popup_field_descriptions = []
		for field_name in ordered_popup_fields:
			popup_field_description = popup_field_description_factory()
			setattr(popup_field_description, "fieldName", field_name)
			field_alias = ordered_popup_alias_by_name.get(field_name)
			if isinstance(field_alias, str):
				setattr(popup_field_description, "alias", field_alias)
			popup_field_descriptions.append(popup_field_description)
		popup_info.fieldDescriptions = popup_field_descriptions

		current_popup = getattr(layer_cim, "popupInfo", None)
		current_media = (
			getattr(current_popup, "mediaInfos", None)
			if current_popup is not None
			else None
		)
		current_fields = None
		if isinstance(current_media, list) and current_media:
			current_fields = getattr(current_media[0], "fields", None)
		current_popup_field_descriptions = (
			getattr(current_popup, "fieldDescriptions", None)
			if current_popup is not None
			else None
		)
		current_popup_field_names = []
		if isinstance(current_popup_field_descriptions, list):
			current_popup_field_names = [
				str(getattr(item, "fieldName", None) or getattr(item, "name", ""))
				for item in current_popup_field_descriptions
			]

		if (
			isinstance(current_fields, list)
			and [str(field) for field in current_fields] == ordered_popup_fields
			and current_popup_field_names == ordered_popup_fields
		):
			LOGGER.debug(
				"set_cim_popup_info_fields_by_yml: already correct for '%s' (field_count=%s)",
				layer_name,
				len(ordered_popup_fields),
			)
			return True, False, f"Configured {len(ordered_popup_fields)} popup field(s)"

		layer_cim.popupInfo = popup_info
		layer.setDefinition(layer_cim)
		LOGGER.debug(
			"set_cim_popup_info_fields_by_yml: updated '%s' (field_count=%s)",
			layer_name,
			len(ordered_popup_fields),
		)
		return False, True, f"Configured {len(ordered_popup_fields)} popup field(s)"
	except Exception as exc:
		LOGGER.warning("set_cim_popup_info_fields_by_yml: failed for '%s': %s", layer_name, exc)
		return None, False, f"Could not set popupInfo from cols: {exc}"




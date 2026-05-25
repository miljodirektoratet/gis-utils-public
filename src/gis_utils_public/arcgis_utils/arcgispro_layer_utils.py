"""ArcGIS Pro layer-related helper functions.

Public functions:
- add_layers_from_config_sde_to_map: Add YAML-configured layers from SDE to map.
- apply_lyrx_to_layer: Apply LYRX transfer to a map layer.
- apply_lyrx_to_map_layers_from_config: Apply LYRX transfer to YAML-defined map layers.
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

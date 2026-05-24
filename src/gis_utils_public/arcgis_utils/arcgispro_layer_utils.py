"""ArcGIS Pro layer-related helper functions.

Public functions:
- add_layers_from_config_sde_to_map: Add YAML-configured layers from SDE to map.
"""

import logging
import os
from typing import Any

from .yaml_config_arcgis import resolve_layer_sde_connection_path

LOGGER = logging.getLogger(__name__)


def _iter_layer_entries(service_def_config: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
	"""Return YAML layer entries excluding top-level map config.

	:param service_def_config: Full map service definition config dictionary.
	:return: Ordered list of ``(layer_name, layer_config)`` pairs.
	"""
	if not isinstance(service_def_config, dict):
		return []

	return [
		(layer_name, layer_cfg)
		for layer_name, layer_cfg in service_def_config.items()
		if layer_name != "map" and isinstance(layer_cfg, dict)
	]


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

	result: dict[str, Any] = {
		"layer_name": layer_name,
		"sde_connection": sde_connection_path,
		"dataset_path": None,
		"tried_paths": [],
		"added": False,
		"error": None,
	}

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
	layer_entries = _iter_layer_entries(service_def_config)
	results: list[dict[str, Any]] = []

	LOGGER.info("Add layers from SDE in config order")

	for layer_name, layer_config in layer_entries:
		LOGGER.info("-> Add layer from SDE source: %s", layer_name)
		try:
			sde_connection_path = resolve_layer_sde_connection_path(
				service_def_config=service_def_config,
				layer_config=layer_config,
				env=env,
				fallback_path=fallback_sde_path,
			)
		except Exception as exc:
			layer_result = {
				"layer_name": layer_name,
				"sde_connection": None,
				"dataset_path": None,
				"tried_paths": [],
				"added": False,
				"error": str(exc),
			}
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
			LOGGER.info("-> Added layer '%s' from %s", layer_name, layer_result.get("dataset_path"))
		else:
			LOGGER.warning("-> Failed adding layer '%s': %s", layer_name, layer_result.get("error"))
		results.append(layer_result)

	added_count = sum(1 for result in results if bool(result.get("added")))
	LOGGER.info("-> Added %d/%d layer(s) to map", added_count, len(layer_entries))

	return {
		"layer_results": results,
		"layer_total": len(layer_entries),
		"layers_added_count": added_count,
	}

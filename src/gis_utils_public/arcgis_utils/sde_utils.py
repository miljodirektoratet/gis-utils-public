"""SDE (Enterprise Geodatabase) helper functions.

Public functions:
- apply_sde_field_design: Apply field design (alias and optional type/length/nullable) to an SDE dataset.
"""

import logging
from typing import Any

from .arcgispro_layer_utils import (
	_generate_field_alias,
	_is_system_field,
	_normalize_field_alias_overrides,
	_normalize_field_name,
)

LOGGER = logging.getLogger(__name__)


def apply_sde_field_design(
	dataset_path: str,
	field_alias_overrides: dict[str, str] | None = None,
	field_design_overrides: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
	"""Apply field design to an SDE table or feature class using AlterFields.

	Applies field aliases (auto-generated or from YAML config) and optionally
	field type, length, and nullable when explicitly provided per field.

	Parameter rules per field passed to ``arcpy.management.AlterFields``:

	- ``new_field_name``: always ``#`` — fields are never renamed
	- ``new_field_alias``: resolved alias from override or auto-generation
	- ``new_field_type``: ``#`` unless present in ``field_design_overrides``
	- ``new_field_length``: ``#`` unless present in ``field_design_overrides``
	- ``new_field_is_nullable``: ``#`` unless present in ``field_design_overrides``
	- ``clear_field_alias``: always ``false``

	System fields (OID, Geometry, GlobalID, computed) are skipped.
	Fields referenced in config that do not exist on the dataset are reported
	in the ``missing`` list and skipped.

	:param dataset_path: Full path to SDE table or feature class.
	:param field_alias_overrides: Optional field-name to alias override mapping from YAML config.
	:param field_design_overrides: Optional per-field design overrides dict. Each key is a
		field name; each value may contain ``type``, ``length``, ``is_nullable``.
	:return: Summary dict with ``changed``, ``missing``, ``skipped``, ``errors`` keys.
	"""
	import arcpy

	alias_overrides = _normalize_field_alias_overrides(field_alias_overrides)
	design_overrides = field_design_overrides if isinstance(field_design_overrides, dict) else {}

	missing: list[str] = []
	skipped: list[str] = []
	errors: list[dict[str, str]] = []

	try:
		fields = arcpy.ListFields(dataset_path)
	except Exception as exc:
		return {
			"dataset_path": dataset_path,
			"exists": False,
			"error": str(exc),
			"changed": 0,
			"missing": missing,
			"skipped": skipped,
			"errors": errors,
		}

	if not fields:
		return {
			"dataset_path": dataset_path,
			"exists": True,
			"error": None,
			"changed": 0,
			"missing": missing,
			"skipped": skipped,
			"errors": errors,
		}

	# Build lookup of normalized name -> actual field object
	field_lookup: dict[str, Any] = {}
	for field in fields:
		actual_name = getattr(field, "name", None)
		if not isinstance(actual_name, str):
			continue
		normalized = _normalize_field_name(actual_name)
		if normalized and normalized not in field_lookup:
			field_lookup[normalized] = field

	# Validate any explicitly referenced override fields are present on dataset
	for override_name in alias_overrides:
		if override_name not in field_lookup:
			missing.append(override_name)
			LOGGER.warning(
				"apply_sde_field_design: field '%s' not found on dataset '%s' — skipping",
				override_name,
				dataset_path,
			)

	# Build field_description rows for AlterFields
	field_description: list[list[str]] = []
	for field in fields:
		field_name = getattr(field, "name", None)
		if not isinstance(field_name, str) or not field_name:
			continue

		if _is_system_field(field):
			skipped.append(field_name)
			continue

		normalized = _normalize_field_name(field_name)
		resolved_alias = alias_overrides.get(normalized, _generate_field_alias(field_name))

		field_design = design_overrides.get(field_name, {}) if design_overrides else {}
		new_type = str(field_design.get("type", "#")) if field_design.get("type") else "#"
		new_length = str(field_design.get("length", "#")) if field_design.get("length") is not None else "#"
		new_nullable = str(field_design.get("is_nullable", "#")).lower() if field_design.get("is_nullable") is not None else "#"

		field_description.append([
			field_name,
			"#",
			resolved_alias,
			new_type,
			new_length,
			new_nullable,
			"false",
		])

	if not field_description:
		return {
			"dataset_path": dataset_path,
			"exists": True,
			"error": None,
			"changed": 0,
			"missing": missing,
			"skipped": skipped,
			"errors": errors,
		}

	try:
		arcpy.management.AlterFields(
			in_table=dataset_path,
			field_description=field_description,
		)
		changed = len(field_description)
		LOGGER.debug(
			"apply_sde_field_design: updated '%s' (changed=%s, skipped=%s, missing=%s)",
			dataset_path,
			changed,
			len(skipped),
			len(missing),
		)
	except Exception as exc:
		LOGGER.warning(
			"apply_sde_field_design: AlterFields failed for '%s': %s",
			dataset_path,
			exc,
		)
		errors.append({"dataset_path": dataset_path, "error": str(exc)})
		changed = 0

	return {
		"dataset_path": dataset_path,
		"exists": True,
		"error": None,
		"changed": changed,
		"missing": missing,
		"skipped": skipped,
		"errors": errors,
	}

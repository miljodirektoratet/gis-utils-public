"""SDE (Enterprise Geodatabase) helper functions.

Public functions:
- apply_sde_field_design: Apply field design (alias and optional type/length/nullable) to an SDE dataset.
"""

import logging
from typing import Any

from .field_utils import (
	generate_field_alias,
	is_system_field,
	normalize_field_alias_overrides,
	normalize_field_name,
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

	alias_overrides = normalize_field_alias_overrides(field_alias_overrides)
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
		normalized = normalize_field_name(actual_name)
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

		if is_system_field(field):
			skipped.append(field_name)
			continue

		normalized = normalize_field_name(field_name) or field_name.strip().lower()
		resolved_alias = alias_overrides.get(normalized, generate_field_alias(field_name))

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


def compute_expected_field_aliases(
	dataset_path: str,
	field_alias_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
	"""Compute expected field aliases for a dataset without mutation.

	Used for validation: determine what aliases should be applied based on
	config overrides and auto-generation rules.

	:param dataset_path: Full path to SDE dataset or feature class.
	:param field_alias_overrides: Optional field-name to alias override mapping.
	:return: Dictionary mapping field names to expected aliases (system fields excluded).
	"""
	import arcpy

	expected: dict[str, str] = {}
	alias_overrides = normalize_field_alias_overrides(field_alias_overrides)

	try:
		fields = arcpy.ListFields(dataset_path)
	except Exception:
		return {}

	if not fields:
		return {}

	for field in fields:
		field_name = getattr(field, "name", None)
		if not isinstance(field_name, str):
			continue

		if is_system_field(field):
			continue

		normalized_field_name = normalize_field_name(field_name) or field_name.strip().lower()
		resolved_alias = alias_overrides.get(
			normalized_field_name,
			generate_field_alias(field_name),
		)
		expected[field_name] = resolved_alias

	return expected


def validate_field_aliases_on_sde_dataset(
	dataset_path: str,
	field_alias_overrides: dict[str, str] | None = None,
) -> dict[str, Any]:
	"""Validate current field aliases against expected values on SDE dataset.

	Checks each field's current alias against what should be applied based on
	config overrides and auto-generation rules.

	:param dataset_path: Full path to SDE dataset or feature class.
	:param field_alias_overrides: Optional field-name to alias override mapping.
	:return: Dictionary with validation results and mismatches.
	"""
	import arcpy

	expected = compute_expected_field_aliases(dataset_path, field_alias_overrides)

	try:
		fields = arcpy.ListFields(dataset_path)
	except Exception as exc:
		return {
			"dataset_path": dataset_path,
			"exists": False,
			"error": str(exc),
			"fields_checked": 0,
			"fields_matching": 0,
			"fields_mismatched": 0,
			"expected_aliases": expected,
			"mismatches": [],
		}

	if not fields:
		return {
			"dataset_path": dataset_path,
			"exists": True,
			"error": None,
			"fields_checked": 0,
			"fields_matching": 0,
			"fields_mismatched": 0,
			"expected_aliases": expected,
			"mismatches": [],
		}

	mismatches: list[dict[str, str]] = []
	fields_matching = 0

	for field in fields:
		field_name = getattr(field, "name", None)
		if not isinstance(field_name, str):
			continue

		if field_name not in expected:
			continue

		current_alias = getattr(field, "aliasName", field_name)
		expected_alias = expected[field_name]

		if current_alias == expected_alias:
			fields_matching += 1
		else:
			mismatches.append({
				"field_name": field_name,
				"current_alias": current_alias,
				"expected_alias": expected_alias,
			})

	return {
		"dataset_path": dataset_path,
		"exists": True,
		"error": None,
		"fields_checked": len(expected),
		"fields_matching": fields_matching,
		"fields_mismatched": len(mismatches),
		"expected_aliases": expected,
		"mismatches": mismatches,
	}


def apply_table_field_aliases(
	table: Any,
	field_alias_overrides: dict[str, Any] | None = None,
) -> tuple[bool, int, str]:
	"""Apply field aliases to a standalone table using arcpy.management.AlterField.

	Standalone tables in ArcGIS Pro do not support CIM field description manipulation.
	This function uses arcpy.management.AlterField to update aliases directly.

	:param table: ArcGIS standalone table object.
	:param field_alias_overrides: Optional field-name to alias override mapping.
	:return: Tuple ``(applied, field_count, method)``.
	"""
	import arcpy

	table_name = getattr(table, "name", "<unknown>")

	try:
		fields = arcpy.ListFields(table.dataSource)
	except Exception:
		try:
			fields = arcpy.ListFields(table)
		except Exception:
			LOGGER.debug("apply_table_field_aliases: skip '%s' (could not list fields)", table_name)
			return False, 0, "none"

	if not fields:
		LOGGER.debug("apply_table_field_aliases: skip '%s' (no fields)", table_name)
		return False, 0, "none"

	alias_overrides = normalize_field_alias_overrides(field_alias_overrides)
	aliases_applied = 0

	for field in fields:
		field_name = getattr(field, "name", None)
		if not isinstance(field_name, str) or not field_name:
			continue

		if is_system_field(field):
			continue

		normalized_field_name = normalize_field_name(field_name) or field_name.strip().lower()
		resolved_alias = alias_overrides.get(
			normalized_field_name,
			generate_field_alias(field_name),
		)

		try:
			arcpy.management.AlterField(
				table.dataSource,
				field_name,
				new_field_alias=resolved_alias,
			)
			aliases_applied += 1
		except Exception as exc:
			LOGGER.debug(
				"apply_table_field_aliases: failed to update alias for '%s.%s': %s",
				table_name,
				field_name,
				exc,
			)

	if aliases_applied > 0:
		LOGGER.debug(
			"apply_table_field_aliases: updated '%s' (alias_count=%s)",
			table_name,
			aliases_applied,
		)
		return True, aliases_applied, "arcpy.management"

	return False, 0, "none"

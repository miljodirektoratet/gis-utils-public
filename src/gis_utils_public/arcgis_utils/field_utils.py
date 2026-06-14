"""Field helper functions shared across ArcGIS utility modules.

Public functions:
- get_field_data_design: Read current field design (alias, type, length, nullable) from dataset.
- apply_field_data_design: Apply field design changes to dataset. Only attributes present in input are updated.
"""

import re
from typing import Any


def normalize_field_name(name: Any) -> str | None:
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


def normalize_field_alias_overrides(field_alias_overrides: Any) -> dict[str, str]:
	"""Normalize configured field alias overrides by field name.

	:param field_alias_overrides: Raw alias override mapping from config.
	:return: Normalized mapping keyed by normalized field name.
	"""
	if not isinstance(field_alias_overrides, dict):
		return {}

	normalized_overrides: dict[str, str] = {}
	for field_name, alias in field_alias_overrides.items():
		normalized_name = normalize_field_name(field_name)
		if normalized_name is None:
			continue
		if not isinstance(alias, str):
			continue
		cleaned_alias = alias.strip()
		if not cleaned_alias:
			continue
		normalized_overrides[normalized_name] = cleaned_alias
	return normalized_overrides


def is_system_field(field: Any) -> bool:
	"""Return whether a field is a system field (OID, geometry, GlobalID, and computed function fields).
	These fields should not be altered by field configuration, and are excluded from field processing pipelines.

	:param field: ArcPy field-like object.
	:return: ``True`` for OID, geometry, GlobalID, and computed function fields, else ``False``.
	"""
	field_type = getattr(field, "type", None)
	if isinstance(field_type, str) and field_type.strip().lower() in {
		"oid",
		"geometry",
		"globalid",
	}:
		return True

	field_name = normalize_field_name(getattr(field, "name", None))
	if field_name in {"objectid", "shape"}:
		return True

	raw_field_name = getattr(field, "name", None)
	if isinstance(raw_field_name, str) and "(" in raw_field_name and ")" in raw_field_name:
		return True

	return False


def generate_field_alias(field_name: str) -> str:
	"""Generate an automatic field alias from a field name.

	:param field_name: Source field name.
	:return: Generated alias text.
	"""
	
	# Convert snake_case, camelCase and PascalCase to lower case with space separation
	# "field_name" -> "field name", 
  # "fieldName" -> "field name", 
  # "FieldName" -> "field name"
	alias = field_name.replace("_", " ")
	alias = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", alias)
	alias = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", alias)
	alias = re.sub(r"\s+", " ", alias).strip().lower()
	if not alias:
		return field_name

  # Convert back to Norwegian characters
	alias = alias.replace("aa", "å")
	alias = alias.replace("ae", "æ")
	alias = alias.replace("oe", "ø")
	return alias


def get_field_data_design(dataset_path: str) -> dict[str, dict[str, Any]]:
	"""Read current field design from dataset.

	Returns alias, type, length and nullable for all non-system fields.

	:param dataset_path: Full path to SDE table or feature class.
	:return: Mapping of field_name to ``{alias, type, length, nullable}``. Empty dict if dataset not found.
	"""
	import arcpy

	try:
		fields = arcpy.ListFields(dataset_path)
	except Exception:
		return {}

	if not fields:
		return {}

	result: dict[str, dict[str, Any]] = {}
	for field in fields:
		field_name = getattr(field, "name", None)
		if not isinstance(field_name, str) or not field_name:
			continue

		if is_system_field(field):
			continue

		result[field_name] = {
			"alias": getattr(field, "aliasName", field_name),
			"type": getattr(field, "type", None),
			"length": getattr(field, "length", None),
			"nullable": getattr(field, "isNullable", None),
		}

	return result


def apply_field_data_design(
	dataset_path: str,
	field_design: dict[str, dict[str, Any]],
) -> dict[str, Any]:
	"""Apply field design changes to dataset via AlterField.

	Only attributes explicitly present in each field's dict are updated.
	Omit an attribute to leave it unchanged on the dataset.

	Supported attributes per field: ``alias``, ``length``, ``nullable``.
	(``type`` cannot be changed via AlterField after field creation.)

	:param dataset_path: Full path to SDE table or feature class.
	:param field_design: Mapping of field_name to design dict.
		Example: ``{"my_field": {"alias": "My Field", "nullable": False}}``
	:return: Dictionary with ``applied``, ``attempted``, ``errors`` keys.
	"""
	import arcpy
	import logging

	logger = logging.getLogger(__name__)

	applied = 0
	attempted = 0
	errors: list[dict[str, str]] = []

	for field_name, attrs in field_design.items():
		attempted += 1
		try:
			arcpy.management.AlterField(
				in_table=dataset_path,
				field=field_name,
				new_field_alias=attrs.get("alias", "#") or "#",
				new_field_length=attrs.get("length", "#") if attrs.get("length") is not None else "#",
				new_field_is_nullable=attrs.get("nullable", "#") if attrs.get("nullable") is not None else "#",
			)
			applied += 1
			logger.debug(
				"apply_field_data_design: updated '%s.%s' attrs=%s",
				dataset_path,
				field_name,
				list(attrs.keys()),
			)
		except Exception as exc:
			logger.debug(
				"apply_field_data_design: AlterField failed for '%s.%s': %s",
				dataset_path,
				field_name,
				exc,
			)
			errors.append({
				"field_name": field_name,
				"error": str(exc),
			})

	return {
		"applied": applied,
		"attempted": attempted,
		"errors": errors,
	}

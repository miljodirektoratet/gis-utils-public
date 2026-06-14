"""Field helper functions shared across ArcGIS utility modules."""

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

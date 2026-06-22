"""Configuration helpers for ArcGIS map service YAML files.

Public functions:
- load_map_service_config: Load and split map/layer sections from YAML.
- load_map_and_infrastructure_config: Load map YAML together with infrastructure YAML.
- load_map_infrastructure_and_datamodel_config: Load map YAML, infrastructure, and optional datamodel YAML.
- iter_map_service_layer_entries: Return ordered YAML layer entries.
- resolve_datamodel_field_design: Resolve layer field design from datamodel datasets.
- resolve_layer_database_name: Resolve database key from layer/map config.
- resolve_infrastructure_sde_connection_path: Resolve SDE path from infrastructure by database/env/access.
- resolve_infrastructure_datamodel_path: Resolve datamodel path from infrastructure by database.
- resolve_layer_sde_connection_path: Resolve layer/map SDE path with fallback.
- validate_lyr_source_sde_paths: Validate configured datasets against SDE paths.
"""

import logging
import os
from typing import Any, Callable

from ..yaml_config import read_yml_config

LOGGER = logging.getLogger(__name__)


def _normalize_config_values(value: Any) -> Any:
    """Normalize YAML values recursively.

    Trims string values and converts null-like tokens to ``None``.
    For multiline strings, only trailing whitespace is removed to preserve
    indentation semantics.

    :param value: Any parsed YAML value.
    :return: Normalized value with recursive conversion applied.
    """
    if isinstance(value, dict):
        return {key: _normalize_config_values(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_normalize_config_values(item) for item in value]
    if isinstance(value, str):
        # Multiline strings: only trim trailing whitespace to preserve indentation
        if "\n" in value:
            cleaned = value.rstrip()
        # Single-line strings: trim all leading/trailing whitespace
        else:
            cleaned = value.strip()

        # Convert common null-like strings to None
        if cleaned.lower() in {"none", "null", "~"}:
            return None

        # Boolean normalization for quoted string values
        if cleaned.lower() == "true":
            return True
        if cleaned.lower() == "false":
            return False

        return cleaned
    return value


def iter_map_service_layer_entries(
    config: dict[str, Any] | None,
) -> list[tuple[str, dict[str, Any]]]:
    """Return ordered map-service layer entries excluding top-level map config.

    :param config: Parsed map service configuration dictionary.
    :return: Ordered list of ``(layer_name, layer_cfg)`` tuples.
    """
    if not isinstance(config, dict):
        return []

    return [
        (name, cfg)
        for name, cfg in config.items()
        if name != "map" and isinstance(cfg, dict)
    ]


def load_map_service_config(
    conf_file: str | os.PathLike[str],
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Load and split map service configuration.

    :param conf_file: Path to the map service YAML file: ``data_product_map_service_definition.yml``.
    :return: Tuple ``(config, config_map, config_layers)`` where ``config`` is the
        full YAML dict, ``config_map`` is ``config["map"]`` (or ``{}``), and
        ``config_layers`` is a list of ``(layer_name, layer_cfg)`` tuples.
    """
    LOGGER.debug("Loading map service config YAML: %s", conf_file)
    config = _normalize_config_values(read_yml_config(conf_file))
    config_map = config.get("map", {}) if isinstance(config, dict) else {}
    config_layers = iter_map_service_layer_entries(config)
    return config, config_map, config_layers


def load_map_and_infrastructure_config(
    conf_file: str | os.PathLike[str],
    infrastructure_file: str | os.PathLike[str] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[tuple[str, dict[str, Any]]],
    dict[str, Any],
]:
    """Load map service config and optional infrastructure config.

    :param conf_file: Path to the map service YAML file.
    :param infrastructure_file: Optional path to infrastructure YAML file.
    :return: Tuple ``(config, config_map, config_layers, config_infrastructure)``.
    """
    config, config_map, config_layers = load_map_service_config(conf_file)
    config_infrastructure: dict[str, Any] = {}

    if isinstance(infrastructure_file, (str, os.PathLike)):
        infra_path = str(infrastructure_file)
        if infra_path.strip():
            LOGGER.debug("Loading infrastructure config YAML: %s", infra_path)
            raw_infra = _normalize_config_values(read_yml_config(infra_path))
            if isinstance(raw_infra, dict):
                config_infrastructure = raw_infra
            else:
                raise ValueError("Infrastructure config must be a YAML mapping")

    return config, config_map, config_layers, config_infrastructure


def _resolve_datamodel_path(
    map_config: dict[str, Any],
    infrastructure_config: dict[str, Any] | None,
    map_config_path: str | os.PathLike[str],
    datamodel_file: str | os.PathLike[str] | None = None,
) -> str | None:
    """Resolve datamodel YAML path from explicit input or map config.

    Resolution order:
    1) explicit ``datamodel_file`` argument
    2) ``map.datamodel`` in map service config
    3) ``infrastructure.sde_databases[map.database].datamodel``

    Relative paths are resolved relative to the map service config directory.

    :param map_config: Parsed map config dictionary.
    :param map_config_path: Path to map service config file.
    :param datamodel_file: Optional explicit datamodel path override.
    :return: Absolute datamodel path, or ``None`` when not configured.
    """
    candidate = None
    if isinstance(datamodel_file, (str, os.PathLike)):
        candidate = str(datamodel_file).strip()
    if not candidate and isinstance(map_config, dict):
        configured = map_config.get("datamodel")
        if isinstance(configured, str) and configured.strip():
            candidate = configured.strip()
    if not candidate and isinstance(map_config, dict):
        map_database = map_config.get("database")
        if isinstance(map_database, str) and map_database.strip() and isinstance(infrastructure_config, dict):
            return resolve_infrastructure_datamodel_path(
                infrastructure_config=infrastructure_config,
                database_name=map_database.strip(),
                base_dir=os.path.dirname(str(map_config_path)),
            )

    if not candidate:
        return None

    if os.path.isabs(candidate):
        return candidate

    base_dir = os.path.dirname(str(map_config_path))
    return os.path.normpath(os.path.join(base_dir, candidate))


def load_map_infrastructure_and_datamodel_config(
    conf_file: str | os.PathLike[str],
    infrastructure_file: str | os.PathLike[str] | None = None,
    datamodel_file: str | os.PathLike[str] | None = None,
) -> tuple[
    dict[str, Any],
    dict[str, Any],
    list[tuple[str, dict[str, Any]]],
    dict[str, Any],
    dict[str, Any],
]:
    """Load map service config with optional infrastructure and datamodel config.

    :param conf_file: Path to the map service YAML file.
    :param infrastructure_file: Optional path to infrastructure YAML file.
    :param datamodel_file: Optional path to datamodel YAML file.
        When omitted, ``map.datamodel`` is used if present.
    :return: Tuple ``(config, config_map, config_layers, config_infrastructure, config_datamodel)``.
    """
    config, config_map, config_layers, config_infrastructure = (
        load_map_and_infrastructure_config(
            conf_file=conf_file,
            infrastructure_file=infrastructure_file,
        )
    )

    config_datamodel: dict[str, Any] = {}
    datamodel_path = _resolve_datamodel_path(
        map_config=config_map,
        infrastructure_config=config_infrastructure,
        map_config_path=conf_file,
        datamodel_file=datamodel_file,
    )

    if datamodel_path:
        if not os.path.isfile(datamodel_path):
            raise FileNotFoundError(
                f"Datamodel config file does not exist: {datamodel_path}"
            )

        LOGGER.debug("Loading datamodel config YAML: %s", datamodel_path)
        raw_datamodel = _normalize_config_values(read_yml_config(datamodel_path))
        if not isinstance(raw_datamodel, dict):
            raise ValueError("Datamodel config must be a YAML mapping")
        config_datamodel = raw_datamodel

    return config, config_map, config_layers, config_infrastructure, config_datamodel


def resolve_datamodel_field_design(
    datamodel_config: dict[str, Any] | None,
    layer_name: str,
    layer_config: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """Resolve field-design mapping for one layer from datamodel config.

    Matching strategy:
    1) dataset entry key equals ``layer_name``
    2) source.dataset equals layer source.dataset

    Converts datamodel field attributes to pipeline field-design keys:
    - ``is_null`` -> ``nullable``
    - ``data_type`` -> ``type``

    :param datamodel_config: Parsed datamodel YAML dictionary.
    :param layer_name: Layer key name in map service config.
    :param layer_config: Optional layer config dictionary with ``source``.
    :return: Mapping of ``field_name -> field design attrs``.
    """
    if not isinstance(datamodel_config, dict):
        return {}

    datasets = datamodel_config.get("datasets")
    if not isinstance(datasets, dict):
        return {}

    selected_dataset_cfg: dict[str, Any] | None = None

    direct_cfg = datasets.get(layer_name)
    if isinstance(direct_cfg, dict):
        selected_dataset_cfg = direct_cfg

    layer_source = (
        layer_config.get("source", {})
        if isinstance(layer_config, dict)
        else {}
    )
    layer_dataset = layer_source.get("dataset") if isinstance(layer_source, dict) else None

    if selected_dataset_cfg is None and isinstance(layer_dataset, str) and layer_dataset.strip():
        normalized_layer_dataset = layer_dataset.strip()
        for dataset_cfg in datasets.values():
            if not isinstance(dataset_cfg, dict):
                continue
            source_cfg = dataset_cfg.get("source")
            if not isinstance(source_cfg, dict):
                continue
            source_dataset = source_cfg.get("dataset")
            if isinstance(source_dataset, str) and source_dataset.strip() == normalized_layer_dataset:
                selected_dataset_cfg = dataset_cfg
                break

    if not isinstance(selected_dataset_cfg, dict):
        return {}

    fields_cfg = selected_dataset_cfg.get("fields")
    if not isinstance(fields_cfg, dict):
        return {}

    resolved_field_design: dict[str, dict[str, Any]] = {}
    for field_name, attrs in fields_cfg.items():
        if not isinstance(field_name, str) or not field_name.strip():
            continue

        normalized_field_name = field_name.strip()
        field_attrs: dict[str, Any] = {}
        if isinstance(attrs, dict):
            alias = attrs.get("alias")
            if isinstance(alias, str) and alias.strip():
                field_attrs["alias"] = alias.strip()

            nullable_value = attrs.get("nullable")
            if nullable_value is None:
                nullable_value = attrs.get("is_null")
            if isinstance(nullable_value, bool):
                field_attrs["nullable"] = nullable_value

            length_value = attrs.get("length")
            if isinstance(length_value, int):
                field_attrs["length"] = length_value

            type_value = attrs.get("type")
            if type_value is None:
                type_value = attrs.get("data_type")
            if isinstance(type_value, str) and type_value.strip():
                field_attrs["type"] = type_value.strip()

        resolved_field_design[normalized_field_name] = field_attrs

    return resolved_field_design


def resolve_layer_database_name(
    service_def_config: dict[str, Any],
    layer_config: dict[str, Any] | None = None,
) -> str | None:
    """Resolve database key for one layer from ``source.database`` or ``map.database``.

    :param service_def_config: Full map service definition config dictionary.
    :param layer_config: Per-layer config dictionary.
    :return: Resolved database key, or ``None`` when not configured.
    """
    layer_source = (
        (layer_config or {}).get("source", {})
        if isinstance(layer_config, dict)
        else {}
    )
    if isinstance(layer_source, dict):
        layer_database = layer_source.get("database")
        if isinstance(layer_database, str) and layer_database.strip():
            return layer_database.strip()

    map_cfg = (
        (service_def_config or {}).get("map", {})
        if isinstance(service_def_config, dict)
        else {}
    )
    map_database = map_cfg.get("database") if isinstance(map_cfg, dict) else None
    if isinstance(map_database, str) and map_database.strip():
        return map_database.strip()

    return None


def resolve_infrastructure_sde_connection_path(
    infrastructure_config: dict[str, Any],
    database_name: str,
    env: str = "test",
    access_mode: str = "read",
) -> str:
    """Resolve SDE path from infrastructure config using database name.

    Expected structure::

        sde_databases:
          <database_name>:
            test:
              read: \\server\\...\\file.sde
              write: \\server\\...\\file.sde
            prod:
              read: \\server\\...\\file.sde
              write: \\server\\...\\file.sde

    :param infrastructure_config: Parsed infrastructure YAML dictionary.
    :param database_name: Database key from map/layer config.
    :param env: Environment key, typically ``test`` or ``prod``.
    :param access_mode: Access mode key, typically ``read`` or ``write``.
    :return: Resolved SDE connection path.
    :raises ValueError: If required infra keys are missing/invalid.
    """
    if not isinstance(infrastructure_config, dict):
        raise ValueError("Infrastructure config must be a dictionary")

    if not isinstance(database_name, str) or not database_name.strip():
        raise ValueError("database_name must be a non-empty string")

    normalized_env = env if isinstance(env, str) and env.strip() else "test"
    normalized_env = normalized_env.strip().lower()
    normalized_access = access_mode if isinstance(access_mode, str) and access_mode.strip() else "read"
    normalized_access = normalized_access.strip().lower()

    if normalized_access not in {"read", "write"}:
        raise ValueError(
            f"Unsupported access_mode '{access_mode}'. Expected 'read' or 'write'."
        )

    sde_databases = infrastructure_config.get("sde_databases")
    if not isinstance(sde_databases, dict):
        raise ValueError("Missing or invalid 'sde_databases' in infrastructure config")

    database_cfg = sde_databases.get(database_name.strip())
    if not isinstance(database_cfg, dict):
        raise ValueError(
            f"Database '{database_name}' not found in infrastructure.sde_databases"
        )

    env_cfg = database_cfg.get(normalized_env)
    if not isinstance(env_cfg, dict):
        raise ValueError(
            f"Missing environment '{normalized_env}' for database '{database_name}'"
        )

    connection_path = env_cfg.get(normalized_access)
    if not isinstance(connection_path, str) or not connection_path.strip():
        raise ValueError(
            f"Missing '{normalized_access}' connection for database '{database_name}' in env '{normalized_env}'"
        )

    return connection_path.strip()


def resolve_infrastructure_datamodel_path(
    infrastructure_config: dict[str, Any],
    database_name: str,
    base_dir: str | os.PathLike[str] | None = None,
) -> str:
    """Resolve datamodel path from infrastructure config using database key.

    Expected structure::

        sde_databases:
          <database_name>:
            datamodel: <relative-or-absolute-path>

    :param infrastructure_config: Parsed infrastructure YAML dictionary.
    :param database_name: Database key from map/layer config.
    :param base_dir: Optional base directory for resolving relative paths.
    :return: Absolute or normalized datamodel path.
    :raises ValueError: If datamodel mapping is missing/invalid.
    """
    if not isinstance(infrastructure_config, dict):
        raise ValueError("Infrastructure config must be a dictionary")

    if not isinstance(database_name, str) or not database_name.strip():
        raise ValueError("database_name must be a non-empty string")

    sde_databases = infrastructure_config.get("sde_databases")
    if not isinstance(sde_databases, dict):
        raise ValueError("Missing or invalid 'sde_databases' in infrastructure config")

    database_cfg = sde_databases.get(database_name.strip())
    if not isinstance(database_cfg, dict):
        raise ValueError(
            f"Database '{database_name}' not found in infrastructure.sde_databases"
        )

    datamodel_value = database_cfg.get("datamodel")
    if not isinstance(datamodel_value, str) or not datamodel_value.strip():
        raise ValueError(
            f"Missing 'datamodel' for database '{database_name}' in infrastructure.sde_databases"
        )

    normalized_datamodel = datamodel_value.strip()
    if os.path.isabs(normalized_datamodel):
        return normalized_datamodel

    if isinstance(base_dir, (str, os.PathLike)) and str(base_dir).strip():
        return os.path.normpath(os.path.join(str(base_dir), normalized_datamodel))

    return os.path.normpath(normalized_datamodel)


def resolve_layer_sde_connection_path(
    service_def_config: dict[str, Any],
    layer_config: dict[str, Any] | None = None,
    infrastructure_config: dict[str, Any] | None = None,
    env: str = "test",
    access_mode: str = "read",
    fallback_path: str | None = None,
) -> str:
    """Resolve SDE connection path from layer/map config with fallback.

    Priority:
    1) Resolve ``source.database`` (layer) or ``map.database`` (map)
    2) Resolve SDE path via ``infrastructure_config.sde_databases`` using env/access
    3) ``fallback_path``

    :param service_def_config: Full map service definition config dictionary.
    :param layer_config: Per-layer config dictionary.
    :param infrastructure_config: Optional infrastructure config dictionary.
    :param env: Environment key used for infrastructure lookup.
    :param access_mode: Access mode used for infrastructure lookup.
    :param fallback_path: Optional fallback SDE path.
    :return: Resolved SDE connection path.
    :raises ValueError: If no valid SDE path can be resolved.
    """
    resolved_database = resolve_layer_database_name(
        service_def_config=service_def_config,
        layer_config=layer_config,
    )
    if isinstance(resolved_database, str) and resolved_database.strip():
        if not (isinstance(infrastructure_config, dict) and infrastructure_config):
            raise ValueError(
                "database key resolved from config, but infrastructure_config is missing"
            )

        return resolve_infrastructure_sde_connection_path(
            infrastructure_config=infrastructure_config,
            database_name=resolved_database.strip(),
            env=env,
            access_mode=access_mode,
        )

    if isinstance(fallback_path, str) and fallback_path.strip():
        return fallback_path.strip()

    raise ValueError(
        "No SDE connection path found. Set source.database or map.database and provide "
        "infrastructure_config, or provide fallback_path."
    )


# --- Helpers for <data_product>_map_service_definition.yaml files ---
def validate_lyr_source_sde_paths(
    config: dict[str, Any] | None,
    infrastructure_config: dict[str, Any] | None = None,
    sde_path: str | None = None,
    layers_dict: list[tuple[str, dict[str, Any]]] | None = None,
    env: str = "test",
    access_mode: str = "read",
    emit: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Validate layer source dataset paths against SDE.

    :param config: Parsed map service configuration.
    :param infrastructure_config: Optional infrastructure config for database-name resolution.
    :param sde_path: Optional SDE connection path override.
    :param layers_dict: Optional list of (layer_name, layer_cfg) tuples.
    :param env: Environment key for SDE resolution.
    :param access_mode: Access mode used for infrastructure lookup.
    :param emit: Optional output callback. Defaults to ``print``.
    :return: Validation report list per layer.
    """
    LOGGER.info("Validating layer source SDE paths")
    out_msg = emit if callable(emit) else print
    try:
        import arcpy
    except Exception as exc:
        raise RuntimeError(
            "ArcPy is required for validate_lyr_source_sde_paths. "
            "Make sure the notebook kernel uses a valid ArcGIS Pro Python environment."
        ) from exc

    if layers_dict is None:
        layers_dict = iter_map_service_layer_entries(config)

    if sde_path is None and isinstance(config, dict):
        try:
            sde_path = resolve_layer_sde_connection_path(
                service_def_config=config,
                layer_config=None,
                infrastructure_config=infrastructure_config,
                env=env,
                access_mode=access_mode,
            )
        except Exception:
            sde_path = None

    report = []
    for layer_name, layer_cfg in layers_dict:
        feature_dataset, dataset = (
            (
                layer_cfg.get("source", {}).get("feature_dataset"),
                layer_cfg.get("source", {}).get("dataset"),
            )
            if isinstance(layer_cfg.get("source"), dict)
            else (None, None)
        )

        out_msg(f"\nLayer: {layer_name}")
        out_msg(f"  resolved_sde_path: {sde_path}")
        out_msg(f"  feature_dataset: {feature_dataset}")
        out_msg(f"  dataset: {dataset}")

        if not sde_path:
            out_msg("  [MISSING] No SDE connection resolved for this layer.")
            report.append(
                {
                    "layer": layer_name,
                    "ok": False,
                    "reason": "missing_sde_connection",
                }
            )
            continue
        if not feature_dataset or not dataset:
            out_msg("  [MISSING] source.feature_dataset and/or source.dataset.")
            report.append(
                {
                    "layer": layer_name,
                    "ok": False,
                    "reason": "missing_dataset_config",
                }
            )
            continue

        ds_path_via_fd = os.path.join(sde_path, feature_dataset, dataset)
        ds_path_direct = os.path.join(sde_path, dataset)
        exists_via_fd = bool(arcpy.Exists(ds_path_via_fd))
        exists_direct = bool(arcpy.Exists(ds_path_direct))

        out_msg(
            f"  [{'OK' if exists_via_fd else 'MISSING'}] dataset via feature_dataset: {ds_path_via_fd}"
        )
        out_msg(
            f"  [{'OK' if exists_direct else 'MISSING'}] dataset direct: {ds_path_direct}"
        )

        report.append(
            {
                "layer": layer_name,
                "ok": exists_via_fd or exists_direct,
                "sde_connection": sde_path,
                "dataset_via_feature_dataset": ds_path_via_fd,
                "dataset_direct": ds_path_direct,
                "exists_via_feature_dataset": exists_via_fd,
                "exists_direct": exists_direct,
            }
        )

    return report

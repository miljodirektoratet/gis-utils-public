"""Configuration helpers for ArcGIS map service YAML files.

Public functions:
- load_map_service_config: Load and split map/layer sections from YAML.
- load_map_and_infrastructure_config: Load map YAML together with infrastructure YAML.
- iter_map_service_layer_entries: Return ordered YAML layer entries.
- resolve_sde_connection_value: Resolve SDE path from env-keyed or direct config.
- resolve_infrastructure_sde_connection_path: Resolve SDE path from infrastructure by database/env/access.
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
    LOGGER.info("Loading map service config YAML: %s", conf_file)
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
            LOGGER.info("Loading infrastructure config YAML: %s", infra_path)
            raw_infra = _normalize_config_values(read_yml_config(infra_path))
            if isinstance(raw_infra, dict):
                config_infrastructure = raw_infra
            else:
                raise ValueError("Infrastructure config must be a YAML mapping")

    return config, config_map, config_layers, config_infrastructure


def resolve_sde_connection_value(
    sde_config: dict[str, str] | str | None, env: str = "test"
) -> str | None:
    """Resolve an SDE connection path from config.

    :param sde_config: SDE config as env-keyed dict or direct path string.
    :param env: Preferred environment key.
    :return: Resolved SDE connection path string, or ``None`` if not found.

    Example::

        resolve_sde_connection_value(
            {"test": r"C:/connections/test.sde", "prod": r"C:/connections/prod.sde"},
            env="test",
        )
        # output: "C:/connections/test.sde"

        resolve_sde_connection_value(r"C:/connections/shared.sde")
        # output: "C:/connections/shared.sde"
    """
    LOGGER.debug("Resolving SDE connection for env: %s", env)
    if isinstance(sde_config, dict):
        preferred = sde_config.get(env)
        if isinstance(preferred, str) and preferred.strip():
            return preferred.strip()
        for value in sde_config.values():
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None
    if isinstance(sde_config, str) and sde_config.strip():
        return sde_config.strip()
    return None


def _looks_like_sde_path(value: str | None) -> bool:
    """Return whether a value appears to be a direct SDE file path.

    :param value: Candidate value.
    :return: ``True`` when the value looks like a file path to ``.sde``.
    """
    if not isinstance(value, str):
        return False
    normalized = value.strip()
    if not normalized:
        return False
    return normalized.lower().endswith(".sde") or "\\" in normalized or "/" in normalized


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
    1) ``layer_config.source.sde_connection`` (string)
    2) ``service_def_config.map.sde_connection[env]`` (dict) or string
    3) Resolve database name via ``infrastructure_config.sde_databases``
    4) ``fallback_path``

    :param service_def_config: Full map service definition config dictionary.
    :param layer_config: Per-layer config dictionary.
    :param infrastructure_config: Optional infrastructure config dictionary.
    :param env: Environment key used for map-level dict config.
    :param access_mode: Access mode used for infrastructure lookup.
    :param fallback_path: Optional fallback SDE path.
    :return: Resolved SDE connection path.
    :raises ValueError: If no valid SDE path can be resolved.
    """
    layer_source = (
        (layer_config or {}).get("source", {})
        if isinstance(layer_config, dict)
        else {}
    )
    map_cfg = (
        (service_def_config or {}).get("map", {})
        if isinstance(service_def_config, dict)
        else {}
    )

    layer_sde = layer_source.get("sde_connection")
    if isinstance(layer_sde, str) and layer_sde.strip():
        normalized_layer_sde = layer_sde.strip()
        if _looks_like_sde_path(normalized_layer_sde):
            return normalized_layer_sde

        if isinstance(infrastructure_config, dict) and infrastructure_config:
            return resolve_infrastructure_sde_connection_path(
                infrastructure_config=infrastructure_config,
                database_name=normalized_layer_sde,
                env=env,
                access_mode=access_mode,
            )

        raise ValueError(
            "Layer source.sde_connection is a database name, but infrastructure_config is missing"
        )

    map_sde = map_cfg.get("sde_connection")
    resolved_map_sde = resolve_sde_connection_value(sde_config=map_sde, env=env)
    if isinstance(resolved_map_sde, str) and resolved_map_sde.strip():
        normalized_map_sde = resolved_map_sde.strip()
        if _looks_like_sde_path(normalized_map_sde):
            return normalized_map_sde

        if isinstance(infrastructure_config, dict) and infrastructure_config:
            return resolve_infrastructure_sde_connection_path(
                infrastructure_config=infrastructure_config,
                database_name=normalized_map_sde,
                env=env,
                access_mode=access_mode,
            )

        raise ValueError(
            "map.sde_connection resolved to a database name, but infrastructure_config is missing"
        )

    if isinstance(fallback_path, str) and fallback_path.strip():
        return fallback_path.strip()

    raise ValueError(
        "No SDE connection path found. Set source.sde_connection as path/database, "
        "or map.sde_connection for selected env, or provide infrastructure_config/fallback_path."
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
        out_msg(f"  sde_connection: {sde_path}")
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

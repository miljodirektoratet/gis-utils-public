"""Configuration helpers for the YAML config files:
- ArcGIS Map Service Definition: <data-product>_map_service_definition.yml
- ..
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


def load_map_service_config(
    conf_file: str | os.PathLike[str],
) -> tuple[dict[str, Any], dict[str, Any], list[tuple[str, dict[str, Any]]]]:
    """Load and split map service configuration.

    :param conf_file: Path to the map service YAML file: ``data_product_map_service_definition.yml``.
    :return: Tuple ``(config, config_map, config_layers)`` where ``config`` is the
        full YAML dict, ``config_map`` is ``config["map"]`` (or ``{}``), and
        ``config_layers`` is a list of ``(layer_name, layer_cfg)`` tuples.
    """
    LOGGER.debug("Loading map service config: %s", conf_file)
    config = _normalize_config_values(read_yml_config(conf_file))
    config_map = config.get("map", {}) if isinstance(config, dict) else {}
    config_layers = (
        [
            (name, cfg)
            for name, cfg in config.items()
            if name != "map" and isinstance(cfg, dict)
        ]
        if isinstance(config, dict)
        else []
    )
    return config, config_map, config_layers


def resolve_sde_connection(
    sde_config: dict[str, str] | str | None, env: str = "test"
) -> str | None:
    """Resolve an SDE connection path from config.

    :param sde_config: SDE config as env-keyed dict or direct path string.
    :param env: Preferred environment key.
    :return: Resolved SDE connection path string, or ``None`` if not found.

    Example::

        resolve_sde_connection(
            {"test": r"C:/connections/test.sde", "prod": r"C:/connections/prod.sde"},
            env="test",
        )
        # output: "C:/connections/test.sde"

        resolve_sde_connection(r"C:/connections/shared.sde")
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


# --- Helpers for <data_product>_map_service_definition.yaml files ---
def validate_lyr_source_sde_paths(
    config: dict[str, Any] | None,
    sde_path: str | None = None,
    layers_dict: list[tuple[str, dict[str, Any]]] | None = None,
    emit: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    """Validate layer source dataset paths against SDE.

    :param config: Parsed map service configuration.
    :param sde_path: Optional SDE connection path override.
    :param layers_dict: Optional list of (layer_name, layer_cfg) tuples.
    :param emit: Optional output callback. Defaults to ``print``.
    :return: Validation report list per layer.
    """
    LOGGER.debug("Validating layer source SDE paths")
    out_msg = emit if callable(emit) else print
    try:
        import arcpy
    except Exception as exc:
        raise RuntimeError(
            "ArcPy is required for validate_lyr_source_sde_paths. "
            "Make sure the notebook kernel uses a valid ArcGIS Pro Python environment."
        ) from exc

    if layers_dict is None:
        layers_dict = (
            [
                (name, cfg)
                for name, cfg in config.items()
                if name != "map" and isinstance(cfg, dict)
            ]
            if isinstance(config, dict)
            else []
        )

    if sde_path is None and isinstance(config, dict):
        map_cfg = config.get("map", {}) if isinstance(config.get("map"), dict) else {}
        sde_path = resolve_sde_connection(map_cfg.get("sde_connection"))

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

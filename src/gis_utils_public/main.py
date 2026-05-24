"""Test entrypoint for gis-utils-public."""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version


LOGGER = logging.getLogger(__name__)


def hello() -> None:
    """
    Display welcome message and package version information.

    :return: None.
    """
    version_missing = False
    try:
        package_version = version("gis-utils-public")
    except PackageNotFoundError:
        package_version = "unknown"
        version_missing = True

    LOGGER.info("Hello from gis-utils-public!")
    LOGGER.info("Version: %s", package_version)
    if version_missing:
        LOGGER.warning("Version metadata not available in this runtime.")


if __name__ == "__main__":
    hello()

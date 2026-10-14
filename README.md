# gis-utils-public

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub Release](https://img.shields.io/github/v/release/miljodirektoratet/gis-utils-public?logo=python)](https://github.com/miljodirektoratet/gis-utils-public/releases)
[![CI Python](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/gis-utils-public/ci-python.yml?branch=main&label=CI%20Python&style=flat)](https://github.com/miljodirektoratet/gis-utils-public/actions/workflows/ci-python.yml)
[![CD Python](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/gis-utils-public/cd-python.yml?label=CD%20Python&style=flat)](https://github.com/miljodirektoratet/gis-utils-public/actions/workflows/cd-python.yml)

GIS utilities for the GIS platform at the Norwegian Environment Agency
(miljødirektoratet).

This package contains both **open-gis code** (portable to any Python environment) and
**ArcGIS-dependent code** (requires ArcGIS Pro or ArcGIS Online). The design ensures
that open-gis functionality works anywhere, while ArcGIS code is only loaded when
explicitly used.

**Table of Contents**

- [Package Architecture](#package-architecture)
- [Installation \& Usage](#installation--usage)
- [Guidelines](#guidelines)
- [Workflow Statuses](#workflow-statuses)
- [Package Installation](#package-installation)
- [Development](#development)
- [Deployment (Git Tags)](#deployment-git-tags)

## Package Architecture

### Open-GIS Code (Portable)

**Location:** Root of package (`src/gis_utils_public/`)

**Characteristics:**

- No ArcGIS dependencies
- Works in any Python environment (CI/CD, non-ArcGIS machines, etc.)
- Imported directly in `__init__.py`
- Example: `src/gis_utils_public/main.py`

**Import pattern:**

```python
# Safe in any environment
from gis_utils_public import main
main()
```

### ArcGIS-Dependent Code

**Location:** `src/gis_utils_public/arcgis_utils/`

**Characteristics:**

- Requires ArcGIS Pro or ArcGIS Online connection
- Only loaded when explicitly accessed
- Only tested locally, not tested on CI-runners
- NOT exported explicitly in `__init__.py`
- Safe to install in any environment—ArcGIS modules are only imported when used
- Examples: `arcgis_utils/agol_user_admin.py`

**Import pattern:**

```python
# Only loads when you explicitly import from arcgis_utils
from gis_utils_public.arcgis_utils.user_admin import agol_add_users_to_group

# This function requires an authenticated GIS object
agol_add_users_to_group(gis, oidc_users, arcgis_users, group_name)
```

### Why This Design?

1. **CI/CD Compatibility:** Package installs on Ubuntu CI without ArcGIS errors
2. **Flexible Deployment:** Same package works in:
   - Local development (ArcGIS Pro)
   - ArcGIS Online notebooks
   - CI/CD pipelines
   - Non-ArcGIS cloud environments
3. **No Silent Failures:** You only import ArcGIS code when you need it

## Installation & Usage

### Non-ArcGIS Environments (Linux, macOS, Windows without ArcGIS Pro)

Use open-gis code only (e.g. don't load functions from arcgis_utils). The package works
in any Python 3.11+ environment.

**Recommended: Use `uv` for faster, simpler dependency management.**
[Install uv](https://docs.astral.sh/uv/getting-started/) if you don't have it.

**Option 1: Install with `uv` (recommended, fast)**

```bash
# Install uv if you don't have it: https://docs.astral.sh/uv/getting-started/
uv pip install "git+https://github.com/miljodirektoratet/gis-utils-public.git@main"

# Or from a release tag
uv pip install "git+https://github.com/miljodirektoratet/gis-utils-public.git@v0.0.6"

# Use open-gis functionality
python -m gis_utils_public
```

**Option 2: Install with `pip` (standard)**

```bash
pip install "git+https://github.com/miljodirektoratet/gis-utils-public.git@main"

# Or from a release tag
pip install "git+https://github.com/miljodirektoratet/gis-utils-public.git@v0.0.6"

# Use open-gis functionality
python -m gis_utils_public
```

**Option 3: Install from GitHub ZIP (no git required)**

```bash
# From main branch
pip install "https://github.com/miljodirektoratet/gis-utils-public/archive/refs/heads/main.zip"

# Or from a release tag
pip install "https://github.com/miljodirektoratet/gis-utils-public/archive/refs/tags/v0.0.6.zip"
```

ArcGIS modules are not loaded on package install, so no errors occur even though they're
part of the package.

### ArcGIS Pro Environments (Windows with ArcGIS Pro 3.5+)

Use both open-gis and ArcGIS code. **Conda is required** because ArcGIS and ArcPy are
only available from Esri's conda channel (not pip).

```powershell
# Create a Conda environment with ArcGIS Pro 3.5 (required for ArcGIS/ArcPy)
conda env create -f environment.yml -p ./env
conda activate ./env

# Install package (or install from git/release tag)
pip install -e .

# Use open-gis code
python -m gis_utils_public

# Use ArcGIS code (now that ArcGIS/ArcPy is available)
python -c "
from arcgis.gis import GIS
from gis_utils_public import arcgis_utils

gis = GIS('home')
arcgis_utils.agol_user_admin.agol_add_users_to_group(
    gis=gis,
    oidc_brukere=['user@example.com'],
    arcgis_brukere=['arcgis_user'],
    gruppe_navn='My Group',
    dry_run=True
)
"
```

### ArcGIS Online Notebooks

Load individual modules to reduce credits, see
[demo_upload_module_to_agol.ipynb](./notebooks/demo_upload_module_to_agol.ipynb) for
complete examples.

## Guidelines

- **Code organization**: Keep reusable modules in `src/gis_utils_public/`. Open-gis code
  goes in root; ArcGIS-dependent code goes in `arcgis_utils/`.
- **Public code only**: Share only public-safe helper code. Sensitive tasks or
  infrastructure code stay internal.
- **Security practices**:
  - Never commit passwords, tokens, or other sensitive data. Use key vaults for secret
    management.
  - Secret scanning, CodeQL, and Dependabot are enabled.

### Repository Structure

| File or Directory    | Purpose                               |
| -------------------- | ------------------------------------- |
| src/gis_utils_public | Python package source                 |
| notebooks            | Usage examples and workflow demos     |
| environment.yml      | Conda environment definition (pinned) |
| pyproject.toml       | Python packaging metadata             |

## Workflow Statuses

| Job               | Status                                                                                                                                            | Description                                            |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **CI Python**     | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/gis-utils-public/ci-python.yml?branch=main&label=&style=flat)   | Package install smoke test and package build/inspect   |
| **CD Python**     | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/gis-utils-public/cd-python.yml?label=&style=flat)               | Build package artifacts and publish to GitHub Releases |
| **Security Scan** | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/gis-utils-public/scan-codeql.yml?branch=main&label=&style=flat) | CodeQL security scanning                               |

## Package Installation

For detailed installation instructions and examples for different environments, see the
[Installation & Usage](#installation--usage) section above.

**Quick start for non-ArcGIS environments:**

```bash
# Using uv (fast, recommended)
uv pip install "git+https://github.com/miljodirektoratet/gis-utils-public.git@main"

# Using pip (standard)
pip install "git+https://github.com/miljodirektoratet/gis-utils-public.git@main"

# Run the package
python -m gis_utils_public
```

**Quick start for ArcGIS Pro environments:**

```powershell
conda env create -f environment.yml -p ./env
conda activate ./env
pip install -e .
python -m gis_utils_public
```

## Development

### Open-GIS Development (Any Python 3.11+)

For developing or testing open-gis code without ArcGIS Pro. **`uv` is recommended** for
fast, reproducible development environments.

```bash
# Create virtual environment (optional, but recommended)
uv venv

# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Install with all development dependencies using uv (recommended)
uv pip install -e . --group dev

# Run tests
pytest

# Format and Lint code
ruff check src/
```

### ArcGIS Pro Development

For developing or testing ArcGIS-dependent code. **Conda is required** because
ArcGIS/ArcPy are only available from Esri's conda channel.

```powershell
# Create Conda environment (project-local, required for ArcGIS/ArcPy)
conda env create -f environment.yml -p ./env
conda activate ./env

# Install package with all development dependencies
pip install -e ".[dev]"

# Run tests (tests both open-gis and ArcGIS code)
pytest

# Format and Lint code
ruff check src/
```

**Note:** ArcGIS and ArcPy are conda-only packages from Esri's conda channel (not
available on PyPI). They must be installed through the `environment.yml` conda
environment. The `environment.yml` file includes all pip dependencies from
`pyproject.toml[dev]` for consistency. Use `conda` for ArcGIS development; use `uv` for
open-gis development.

### Existing ArcGIS Pro Environment

If you already have ArcGIS Pro installed, you can develop in that environment:

```powershell
conda activate <your-arcgis-env-name>

# Install package in editable mode with all development dependencies
pip install -e ".[dev]"

# Or install from git
pip install -e "git+https://github.com/miljodirektoratet/gis-utils-public.git#egg=gis-utils-public[dev]"
```

### Requirements

- **Python 3.11–3.13**
- **ArcGIS Pro 3.5+** (optional; via conda only, not pip)
- **Conda** (optional; for environment management with ArcGIS)

## Deployment (Git Tags)

The Python release workflow is tag-driven. Pushing a tag matching `v*.*.*` triggers
`CD | Python Build and Publish`, which builds package artifacts and uploads them to
GitHub Releases.

Before creating a new release tag, update the package version in `pyproject.toml`
(`[project].version`) to match the tag version.

```powershell
# List tags
git tag --list

# Example: create and push a release tag
git tag -a v0.0.6 -m "release v0.0.6"
git push origin v0.0.6

# Delete wrong tag
git tag -d v.0.0.6
```

After deployment, install from the tagged release reference:

```powershell
pip install "git+https://github.com/miljodirektoratet/gis-utils-public.git@v0.0.6"
```

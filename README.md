# arcgis-utils-public

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![GitHub Release](https://img.shields.io/github/v/release/miljodirektoratet/arcgis-utils-public?logo=python)](https://github.com/miljodirektoratet/arcgis-utils-public/releases) [![CI Python](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcgis-utils-public/ci-python.yml?branch=main&label=CI%20Python&style=flat)](https://github.com/miljodirektoratet/arcgis-utils-public/actions/workflows/ci-python.yml) [![CD Python](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcgis-utils-public/cd-python.yml?label=CD%20Python&style=flat)](https://github.com/miljodirektoratet/arcgis-utils-public/actions/workflows/cd-python.yml)

Python utility package for ArcGIS Pro 3.5 and AGOL/ESRI-related tasks at the Norwegian Environment Agency (miljødirektoratet).

**Table of Contents**

- [Guidelines](#guidelines)
- [Workflow Statuses](#workflow-statuses)
- [Package Installation](#package-installation)
- [Module Installation](#module-installation)
- [Development](#development)
- [Deployment (Git Tags)](#deployment-git-tags)

## Guidelines

- **ArcGIS Python**: python utilities intended for ArcGIS Pro 3.5 runtime or ArcGIS Online.
- **Module layout**: keep reusable modules inside `src/arcgis_utils_public` so they can be used both as package imports and as direct module files (for example for AGOL workflows).
- **Public code**: public-safe helper code only, sensitive code actual admin-tasks or infrastructure code is stored internally.
- **Security practices**:
  - Never commit passwords, tokens, or other sensitive data. Use key vaults for secret management.
  - Secret scanning, CodeQL, and Dependabot are enabled.

### Repository Structure

| File or Directory       | Purpose                               |
| ----------------------- | ------------------------------------- |
| src/arcgis_utils_public | Python package source                 |
| notebooks               | Usage examples and workflow demos     |
| environment.yml         | Conda environment definition (pinned) |
| pyproject.toml          | Python packaging metadata             |

## Workflow Statuses

| Job               | Status                                                                                                                                               | Description                                            |
| ----------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **CI Python**     | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcgis-utils-public/ci-python.yml?branch=main&label=&style=flat)   | Package install smoke test and package build/inspect   |
| **CD Python**     | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcgis-utils-public/cd-python.yml?label=&style=flat)               | Build package artifacts and publish to GitHub Releases |
| **Security Scan** | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcgis-utils-public/scan-codeql.yml?branch=main&label=&style=flat) | CodeQL security scanning                               |

## Package Installation

Package installation must be done inside a Python environment compatible with ArcGIS Pro 3.5+ (typically Python 3.11) or ArcGIS Online notebooks (Python 3.13).

If your runtime does not have `git` installed (for example in AGOL notebook environments), use the ZIP-based install commands below instead of `git+https` URLs.

```powershell
# main branch (fast iteration)
pip install "git+https://github.com/miljodirektoratet/arcgis-utils-public.git@main"

# tag (release workflow)
pip install "git+https://github.com/miljodirektoratet/arcgis-utils-public.git@v0.0.3"

# commit (strict reproducibility)
pip install "git+https://github.com/miljodirektoratet/arcgis-utils-public.git@cff3f70b85822c82204c0e66876c240fbebeb563"

# no-git fallback: install from tag ZIP archive
pip install "https://github.com/miljodirektoratet/arcgis-utils-public/archive/refs/tags/v0.0.3.zip"

# run the hello entrypoint
python -m arcgis_utils_public.hello
```

## Module Installation

In AGOL we recommend loading a single module file instead of installing the full package to reduce credits usage. The [demo_upload_module_to_agol.ipynb](./notebooks/demo_upload_module_to_agol.ipynb) notebook shows how to do this using the `load_github_module` function. You can pin to a version tag or a commit hash, or use `main` for quick development.

## Development

This package requires a Conda environment with ArcGIS Pro 3.5 to use ArcPy-dependent functionality.

### Setup

```powershell
# Create environment (project-local)
conda env create -f environment.yml -p ./env
conda activate ./env

# Install package in editable mode
pip install -e .
```

### Install into Existing ArcGIS Pro Environment

If you already have ArcGIS Pro installed with its own Conda environment, you can install this package into that environment without creating a new environment.

```powershell
# Activate your existing ArcGIS Pro environment
conda activate <your-arcgis-env-name>

# Install from source (editable)
pip install -e "git+https://github.com/miljodirektoratet/arcgis-utils-public.git#egg=arcgis-utils-public"

# Or install from a release tag
pip install "git+https://github.com/miljodirektoratet/arcgis-utils-public.git@v0.0.3"

# Or install from main branch
pip install "git+https://github.com/miljodirektoratet/arcgis-utils-public.git@main"
```

**Note:** The `environment.yml` file is a complete standalone environment. It's only needed if you want a dedicated project environment. For installing into an existing ArcGIS Pro environment, use `pip` only.

### Requirements

- **ArcGIS Pro 3.5+** or AGOL notebook environment
- **Conda** (package manager)
- **Python 3.11–3.13**

## Deployment (Git Tags)

The Python release workflow is tag-driven. Pushing a tag matching `v*.*.*` triggers `CD | Python Build and Publish`, which builds package artifacts and uploads them to GitHub Releases.

Before creating a new release tag, update the package version in `pyproject.toml` (`[project].version`) to match the tag version.

```powershell
# List tags
git tag --list

# Example: create and push a release tag
git tag -a v0.0.3 -m "release v0.0.3"
git push origin v0.0.3

# Delete wrong tag
git tag -d v.0.0.3
```

After deployment, install from the tagged release reference:

```powershell
pip install "git+https://github.com/miljodirektoratet/arcgis-utils-public.git@v0.0.3"
```

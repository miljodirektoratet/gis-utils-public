# mdir-arcpy-utils-public

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT) [![GitHub Release](https://img.shields.io/github/v/release/miljodirektoratet/arcpy-utils-public?logo=python)](https://github.com/miljodirektoratet/arcpy-utils-public/releases) [![CI Python](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcpy-utils-public/ci-python.yml?branch=main&label=CI%20Python&style=flat)](https://github.com/miljodirektoratet/arcpy-utils-public/actions/workflows/ci-python.yml) [![CD Python](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcpy-utils-public/cd-python.yml?label=CD%20Python&style=flat)](https://github.com/miljodirektoratet/arcpy-utils-public/actions/workflows/cd-python.yml)

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
- **Module layout**: keep reusable modules inside `src/mdir_arcpy_utils_public` so they can be used both as package imports and as direct module files (for example from AGOL workflows).
- **Public code**: public-safe helper code only, sensitive code actual admin-tasks or infrastructure code is stored internally.
- **Security practices**:
  - Never commit passwords, tokens, or other sensitive data. Use key vaults for secret management.
  - Secret scanning, CodeQL, and Dependabot are enabled.

### Repository Structure

| File or Directory           | Purpose                                          |
| --------------------------- | ------------------------------------------------ |
| src/mdir_arcpy_utils_public | Python package source                            |
| notebooks                   | Usage examples and workflow demos                |
| environment.yml             | Conda environment definition                     |
| pyproject.toml              | Python packaging metadata and Pixi configuration |

## Workflow Statuses

| Job               | Status                                                                                                                                              | Description                                            |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **CI Python**     | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcpy-utils-public/ci-python.yml?branch=main&label=&style=flat)   | Package install smoke test and package build/inspect   |
| **CD Python**     | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcpy-utils-public/cd-python.yml?label=&style=flat)               | Build package artifacts and publish to GitHub Releases |
| **Security Scan** | ![Status](https://img.shields.io/github/actions/workflow/status/miljodirektoratet/arcpy-utils-public/scan-codeql.yml?branch=main&label=&style=flat) | CodeQL security scanning                               |

## Package Installation

```powershell
# main branch (fast iteration)
pip install "git+https://github.com/miljodirektoratet/arcpy-utils-public.git@main"

# tag (release workflow)
pip install "git+https://github.com/miljodirektoratet/arcpy-utils-public.git@v0.0.1"

# commit (strict reproducibility)
pip install "git+https://github.com/miljodirektoratet/arcpy-utils-public.git@cff3f70b85822c82204c0e66876c240fbebeb563"
```

## Module Installation

In AGOL we recommend loading a single module file instead of installing the full package to reduce credits usage. The [demo_agol.ipynb](./notebooks/demo_agol.ipynb) notebook shows how to do this using the `load_github_module` function. You can pin to a version tag or a commit hash, or use `main` for quick development.

## Development

Choose one local environment manager.

### Option A: Conda

```powershell
conda env create -f environment.yml
conda activate mdir-arcpy-utils-public

# Local development package
pip install -e .
```

### Option B: Pixi

```powershell
pixi install
pixi shell
pixi run install-editable
```

## Deployment (Git Tags)

The Python release workflow is tag-driven. Pushing a tag matching `v*.*.*` triggers `CD | Python Build and Publish`, which builds package artifacts and uploads them to GitHub Releases.

```powershell
# List tags
git tag --list

# Example: create and push a release tag
git tag -a v0.0.1 -m "release v0.0.1"
git push origin v0.0.1

# Delete wrong tag
git tag -d v.0.0.1
```

After deployment, install from the tagged release reference:

```powershell
pip install "git+https://github.com/miljodirektoratet/arcpy-utils-public.git@v0.0.1"
```

# Convention for Python Guidance, Code Quality, and Security

This document outlines:

- detailed Python authoring guidance
- code quality tools and quality gates
- security measures and enforcement mechanisms

## Python Authoring Guidance

This section is the detailed convention source for Python authoring patterns in this repository. The execution guidance for Copilot loaded when .py files are being created/edited lives in `.github/instructions/python.instructions.md`. This document complements that lean instruction file with the longer rationale and patterns that do not need to be loaded every turn.

### Design

- Keep functions focused and explicit.
- Prefer readability and maintainability over compact cleverness.
- Avoid deep nesting and hidden state.
- Keep business logic separate from I/O.

### Naming by Intent

| Prefix      | Purpose                                    |
| ----------- | ------------------------------------------ |
| `load_`     | Read external data                         |
| `clean_`    | Normalize values                           |
| `validate_` | Enforce structure/state and fail on errors |
| `check_`    | Verify a condition                         |
| `lookup_`   | Resolve aliases or mappings                |
| `get_`      | Read already-loaded data                   |
| `resolve_`  | Derive value from context                  |
| `create_`   | Build a concrete object or path            |
| `build_`    | Assemble larger result                     |

### Module Flow Pattern

When useful, group non-trivial modules by stage:

1. Load
2. Clean/Normalize
3. Resolve
4. Validate
5. Build/Assemble
6. Runtime Context

### Shared Helpers and References

Prefer existing shared helpers before adding new local wrappers:

- `src/shared/shared_yaml_utils.py`
- `src/shared/shared_config_databases.py`
- `src/shared/shared_config_dataproducts.py`

## Python Style and Convention Rules

This repository follows the following Python style guides:

- **[PEP 8](https://peps.python.org/pep-0008/)** for code style and formatting.
- **[PEP287](https://peps.python.org/pep-0287/)** for docstrings in modules, classes, methods and functions. We use **reStructuredText (reST)**, the default Python documentation format, as it integrates well with tools such as Sphinx for generating documentation.

The table below summarizes the coding standards used in this repository, including any intentional deviations from PEP 8/257 and the tools used to enforce them.

| Practice                                           | PEP8       | Repository              | Tool         | Local check                  | pre-commit | GHA |
| -------------------------------------------------- | ---------- | ----------------------- | ------------ | ---------------------------- | ---------- | --- |
| Max line length                                    | 79         | 88                      | Ruff [E501]  | `uv run ruff check`          | ✅         | ✅  |
| Docstring and comment length                       | 72         | 78                      | not enforced | -                            | -          | -   |
| Docstring convention                               | PEP287     | reStructuredText (reST) | Ruff [D]     | `uv run ruff check`          | ✅         | ✅  |
| Indentation                                        | 4 spaces   | PEP8                    | Ruff [E111]  | `uv run ruff format --check` | ✅         | ✅  |
| Naming convention - variables, functions, methods  | snake_case | PEP8                    | Ruff [N]     | `uv run ruff check`          | ✅         | ✅  |
| Naming convention - variables with constant values | ALL_CAPS   | PEP8                    | Ruff [N]     | `uv run ruff check`          | ✅         | ✅  |
| Naming convention - classes                        | CapWords   | PEP8                    | Ruff [N]     | `uv run ruff check`          | ✅         | ✅  |
| Type checking                                      | -          | enforced                | mypy         | `uv run mypy`                | ✅         | ✅  |
| Language                                           | English    | PEP8                    | not enforced | -                            | -          | -   |

## Code Quality Tools

The following tools help maintain code quality and consistency across the project:

- **[Ruff](https://docs.astral.sh/ruff/):** Fast Python linter and formatter (replaces flake8, black, isort)
- **[Mypy](https://mypy-lang.org/):** Static type checker for Python type hints.
- **[pytest](https://docs.pytest.org/en/stable/):** Testing framework for unit and integration tests
- **[Deptry](https://deptry.com/):** Dependency analyzer to find unused, missing, or misplaced dependencies

For commonly used commands, see the [Command Cheatsheet](../command-cheatsheet.md).

## Security Tools

The following tools help identify and remediate security issues:

- **[Dependabot](https://github.com/dependabot):** Automated dependency updates and vulnerability scanning
- **[CodeQL](https://codeql.github.com/):** Semantic code analysis for security vulnerabilities

## Quality Gates

Code quality is enforced at multiple stages of development:

- **Local Development:** VS Code [settings](../.vscode/settings.json) and [extensions](../.vscode/extensions.json) provide real-time feedback.
- **Task Commands:** Standarized workflows for running quality, testing and dependency checks locally.
- **Pre-commit Hooks:** Automated checks before each commit.
- **GitHub Actions:** Runs the pre-commit configuration, tests, coverage checks, dependency analysis, and package validation on push and pull requests.
- **Dependabot:** Monitors dependencies and creates security update pull requests.
- **CodeQL:** Performs automated security scanning.

### Code Quality, Testing, Dependency, and Security Quality Gates

| Category                | Practice                   | Tool           | Local check                  | pre-commit | GHA | GHA File           |
| ----------------------- | -------------------------- | -------------- | ---------------------------- | ---------- | --- | ------------------ |
| **Code Quality**        | Linting and Formatting     | Ruff           | `task lint` and `task check` | ✅         | ✅  | `ci-python.yml`    |
| **Code Quality**        | Type checking              | mypy           | `task typecheck`             | ✅         | ✅  | `ci-python.yml`    |
| **Testing**             | Unit tests                 | pytest         | `task test`                  | ❌         | ✅  | `ci-python.yml`    |
| **Testing**             | Test coverage              | pytest-cov     | `task test-cov`              | ❌         | ✅  | `ci-python.yml`    |
| **Dependency analysis** | Dependency analysis        | Deptry         | `task deps-check`            | ❌         | ✅  | `ci-python.yml`    |
| **Security**            | Secret detection           | detect-secrets | `task pre-commit`            | ✅         | ✅  | `ci-python.yml`    |
| **Security**            | Dependency vulnerabilities | Dependabot     | ❌                           | ❌         | ✅  | `dependabot.yaml`  |
| **Security**            | Code vulnerabilities       | CodeQL         | ❌                           | ❌         | ✅  | `scan-codeql.yaml` |

## Task Automation

This project uses **Task** as a task runner to provide a consistent interface for development, testing, code quality, and security checks.

Using Task reduces the need to remember individual commands and helps ensure that the same checks are executed locally, in pre-commit hooks, and in GitHub Actions.

Common workflows:

```bash
task check # Fast local quality checks
task ci-local # Full local CI simulation
task --list # Show all available tasks
```

## Local Development Workflow

During active development, use the following command for fast feedback:

```bash
task check
```

This command runs the following checks:

- Code formatting and linting (Ruff)
- Type checking (Mypy)
- Unit tests with coverage (pytest)
- Dependency analysis (Deptry)

Before opening or updating a pull request, run the local CI simulation:

```bash
task ci-local
```

This command executes the full pre-commit configuration, including repository validation, secret detection, notebook checks, and other quality gates that are also enforced in GitHub Actions.

> **Note:** Some pre-commit hooks can significantly increase execution time. For this reason, they are intentionally excluded from task check, which is designed for frequent use during development. The task ci-local command temporarily installs the pre-commit hooks, executes the full pre-commit suite, and then uninstalls the hooks again to keep the local Git environment clean. Running task ci-local before opening or updating a pull request helps catch issues locally before they fail in GitHub Actions.

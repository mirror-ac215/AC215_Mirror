# Shared CI workflow

`ci.yml` runs on every pull request targeting `main`. It detects which component folders changed and invokes the appropriate reusable workflow.

## Current Python service check

The reusable workflow in `python-service-ci.yml` validates one Python service or job. It:

1. installs Python 3.11;
2. installs locked dependencies with `uv sync --frozen --all-groups`;
3. runs `uv run ruff check .`;
4. runs `uv run pytest -v`;
5. builds the component Docker image.

The initial callers validate:

- `services/_template/`, the reference implementation for Python services;
- `services/llm-service/`, whose portable mock-mode image is tested in CI. Real GPU inference is validated separately on an NVIDIA host.

## Add a Python service to CI

When a new Python service is ready, add a path filter and a job to `ci.yml`.

```yaml
# Add this under jobs.changes.steps[1].with.filters:
cv_service:
  - 'services/cv-service/**'

# Add this under jobs:
cv_service:
  name: CV service checks
  needs: changes
  if: needs.changes.outputs.cv_service == 'true'
  uses: ./.github/workflows/python-service-ci.yml
  with:
    service_path: services/cv-service
    image_name: mirror-cv-service-ci
```

To preserve the stable summary gate, also update `ci_summary` in three places:

```yaml
# 1. Add the changed-folder output under jobs.changes.outputs:
cv_service: ${{ steps.filter.outputs.cv_service }}

# 2. Add the component job to ci_summary.needs:
needs: [changes, service_template, cv_service]

# 3. Add these variables to the ci_summary step environment:
CV_SERVICE_CHANGED: ${{ needs.changes.outputs.cv_service }}
CV_SERVICE_RESULT: ${{ needs.cv_service.result }}

# 4. Add this check to the summary shell script:
if [ "$CV_SERVICE_CHANGED" = "true" ] && [ "$CV_SERVICE_RESULT" != "success" ]; then
  echo "CV service checks did not pass: $CV_SERVICE_RESULT"
  exit 1
fi
```

A failing applicable component check must cause the displayed `CI summary` check to fail.

## Requirements for each Python component

Before a component is added to this workflow, it needs:

- `pyproject.toml` and committed `uv.lock` pinned to Python 3.11;
- Ruff and pytest configured as project dependencies;
- tests under `tests/`;
- a Dockerfile that builds from the component directory;
- local commands that pass before opening a pull request:

```bash
uv lock --check
uv run ruff check .
uv run pytest -v
docker build --tag mirror-<component>-ci .
```

Node frontend and database jobs need component-specific CI workflows rather than this Python workflow.

## Action security and updates

Third-party GitHub Actions are pinned to full commit SHAs so a mutable version tag cannot silently change the CI code that runs in this repository. Dependabot checks GitHub Actions dependencies weekly and opens an update pull request when a newer action version is available.

## Branch protection

After a successful PR run establishes the exact check name, protect `main` with the required `CI summary` status check. Do not configure that requirement before observing a real successful GitHub Actions run, because a wrong check name can prevent every PR from merging.

# ACEest Fitness & Gym

[![ACEest CI/CD](https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops/actions/workflows/main.yml/badge.svg)](https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops/actions/workflows/main.yml)

A Flask REST service for gym client management, with an automated build, test and
container pipeline on GitHub Actions and Jenkins. It is a web port of the ACEest
desktop application (the original Tkinter versions are kept in `legacy/` for reference).

## Features

| Area | Endpoints |
| --- | --- |
| Service | `GET /`, `GET /health` |
| Programmes | `GET /programs`, `GET /programs/<code>` (`FL`, `MG`, `BG`) |
| Calculators | `GET /calories?weight=70&program=MG`, `GET /bmi?weight=70&height=175` |
| Clients | `POST /clients`, `GET /clients`, `GET /clients/<name>`, `DELETE /clients/<name>` |
| Client insights | `GET /clients/<name>/bmi`, `/membership`, `/program-plan?level=beginner` |
| Tracking | `GET` and `POST` on `/clients/<name>/progress`, `/workouts`, `/metrics` |
| Export | `GET /export/clients.csv` |

All responses are JSON (except the CSV export). Invalid input returns `400` and an
unknown client or route returns `404`, both with a body of the form `{"error": "..."}`.

Data is stored in SQLite. The database path is read from the `ACEEST_DB`
environment variable (default `aceest_fitness.db`).

## Project structure

```
app.py                      Flask application factory, routes and business logic
wsgi.py                     Gunicorn entry point
requirements.txt            Runtime dependencies (Flask, Gunicorn)
requirements-dev.txt        Runtime + pytest, pytest-cov, flake8
tests/                      Pytest suite: business logic and API tests
Dockerfile                  Multi-stage image (base, test, runtime)
.github/workflows/main.yml  GitHub Actions pipeline
Jenkinsfile                 Jenkins BUILD pipeline
legacy/                     Original Tkinter versions 1.0 to 3.2.4
```

`app.py` keeps the business rules (calorie estimate, BMI, membership status,
programme generator, input validation) in plain functions with no Flask
dependency, so they are unit tested directly. The HTTP routes are thin wrappers
created by `create_app()`, which also lets every test run against its own database.

## Local setup and execution

Requires Python 3.10 or newer (CI tests 3.10, 3.11 and 3.12).

```bash
git clone https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops.git
cd ACEest-Fitness-Gym-Devops
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python app.py
```

The service listens on http://localhost:5000. Try it:

```bash
curl http://localhost:5000/health
curl -X POST http://localhost:5000/clients \
     -H "Content-Type: application/json" \
     -d '{"name": "Ravi", "age": 30, "height": 175, "weight": 70, "program": "MG"}'
curl http://localhost:5000/clients/Ravi/bmi
curl "http://localhost:5000/clients/Ravi/program-plan?level=intermediate"
```

### Running with Docker

```bash
docker build -t aceest-fitness .
docker run --rm -p 5000:5000 -v aceest-data:/data aceest-fitness
```

The named volume keeps the database between container restarts.

## Running the tests manually

```bash
pytest -v                                    # full suite
pytest tests/test_api.py::test_csv_export    # a single test
pytest --cov=app --cov=wsgi --cov-report=term-missing   # with coverage
flake8 .                                     # lint
```

Inside a container, exactly as the pipelines do:

```bash
docker build --target test -t aceest-fitness:test .
docker run --rm aceest-fitness:test
```

The suite has 51 tests with 100% line coverage. The pipelines fail the build if
coverage drops below 90%.

- `tests/test_logic.py` covers the business rules on their own: calorie factors,
  BMI values and categories, membership expiry, the programme generator (with a
  seeded random generator so results are repeatable) and input validation.
- `tests/test_api.py` exercises every endpoint through the Flask test client:
  success responses, validation errors, 404s, upserts, cascade deletes, CSV export
  and the Gunicorn entry point. Each test gets a fresh temporary database
  (`tests/conftest.py`), so tests never depend on each other.

## Docker image design

- **Multi-stage build.** `base` holds the runtime dependencies and code, `test`
  adds pytest, flake8 and the tests, and `runtime` is the default target that
  ships. Test tooling never reaches the deployed image.
- **Small base and cached layers.** `python:3.12-slim`, `pip --no-cache-dir`,
  and `requirements.txt` copied before the code so dependency layers are reused.
  `.dockerignore` keeps Git history, legacy code, docs and local databases out
  of the build context.
- **Least privilege.** The runtime stage runs as a non-root user (`aceest`,
  UID 10001) that can write only to the `/data` volume.
- **Production server.** Gunicorn serves the app, and a `HEALTHCHECK` polls `/health`.

## CI/CD integration

```
 developer push / pull request
            │
            ├──► GitHub Actions ── Build & Lint (3.10/3.11/3.12) ──► Docker image + Pytest in container ──► runtime image smoke test
            │
            └──► Jenkins (polls every 5 min) ── clean venv ──► lint ──► unit tests + coverage ──► Docker build ──► container tests
```

Both pipelines run the same checks from the same files (`requirements-dev.txt`,
`.flake8`, `pytest.ini`, `Dockerfile`), so a change that passes on a laptop
passes in CI.

### GitHub Actions (`.github/workflows/main.yml`)

Runs on every `push` and `pull_request`, on any branch.

1. **Build & Lint.** On Python 3.10, 3.11 and 3.12: install dependencies,
   byte-compile the sources to catch syntax errors, then run flake8.
2. **Docker Image Assembly.** Builds the `test` stage of the Dockerfile.
3. **Automated Testing.** Runs the Pytest suite inside that container, with a
   90% coverage gate.
4. **Runtime image smoke test.** Builds the deployable image, starts it, checks
   `/health`, creates a client, reads its BMI, and confirms the container runs as
   the non-root user.

The Docker job depends on the lint job, so a lint failure stops the pipeline
early. A newer push to the same branch cancels the older run.

### Jenkins (`Jenkinsfile`)

Jenkins is the BUILD environment and a second quality gate, independent of
GitHub's runners. It works on Linux, macOS and Windows agents (shell steps run
with `sh` or `bat` as appropriate).

1. **Checkout.** Wipes the workspace and pulls the latest code from GitHub.
2. **Clean Build Environment.** Creates a fresh virtualenv and installs dependencies.
3. **Compile & Lint.** Byte-compiles the sources and runs flake8.
4. **Unit Tests.** Runs Pytest with a 90% coverage gate, publishes the JUnit
   report and archives `coverage.xml`.
5. **Docker Build.** Builds the runtime image with `--no-cache`, tagged with the
   build number.
6. **Container Tests.** Builds the `test` image and runs the suite inside it.

Setup: install the suggested plugins (they include Pipeline, Git, JUnit,
Timestamper and Workspace Cleanup), then create a **Pipeline** job, choose
*Pipeline script from SCM*, select Git, and enter the repository URL, branch
`*/main` and script path `Jenkinsfile`. The agent needs Python 3.10+, Git and
Docker on its PATH, and the Jenkins user must be allowed to run Docker. The job
polls GitHub every five minutes; a GitHub webhook can replace polling when
Jenkins has a public URL.

## Branching strategy

- `main` is always releasable. Work happens on short-lived branches that are
  merged back with a merge commit or a pull request:
  - `feature/...` for application changes
  - `test/...` for tests
  - `ci/...` and `infra/...` for pipelines and Docker
  - `fix/...` for bug fixes
  - `docs/...` for documentation
- Commit messages follow the Conventional Commits style (`feat:`, `fix:`,
  `test:`, `ci:`, `build:`, `docs:`, `chore:`).
- Every push and pull request is checked by GitHub Actions before merging, and
  Jenkins builds `main` after each merge.

## Version history

The Flask service carries forward the features introduced across the desktop versions.

| Version | Feature introduced | Where it lives now |
| --- | --- | --- |
| 1.0 | Programme workout and diet charts | `/programs` |
| 1.1 | Client profile, calorie estimate | `/clients`, `/calories` |
| 1.1.2 | Multiple clients, CSV export | `/clients`, `/export/clients.csv` |
| 2.0.1, 2.1.2 | SQLite persistence, weekly adherence | `/clients/<name>/progress` |
| 2.2.1 | Adherence history | `GET /clients/<name>/progress` |
| 2.2.4, 3.0.1 | Workouts, body metrics, BMI, goals | `/workouts`, `/metrics`, `/bmi` |
| 3.1.2 | Membership expiry, programme generator | `/membership`, `/program-plan` |
| 3.2.4 | Consolidated release | `APP_VERSION` in `app.py` |

The desktop login screen (a hard-coded `admin`/`admin` account) and the PDF
report were not ported.

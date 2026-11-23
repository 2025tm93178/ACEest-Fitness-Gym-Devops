# ACEest Fitness & Gym

[![ACEest CI/CD](https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops/actions/workflows/main.yml/badge.svg)](https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops/actions/workflows/main.yml)

A Flask REST service for gym client management, delivered by a fully automated CI/CD
pipeline: Git and GitHub, Pytest, Jenkins, SonarQube, Docker and Docker Hub, and
Kubernetes (Minikube) with five deployment strategies and automatic rollback. It is a
web port of the ACEest desktop application; the original Tkinter versions 1.0 to 3.2.4
are kept in `legacy/`.

## Features

| Area | Endpoints |
| --- | --- |
| Service | `GET /`, `GET /health`, `GET /version` |
| Programmes | `GET /programs`, `GET /programs/<code>` (`FL`, `MG`, `BG`) |
| Calculators | `GET /calories?weight=70&program=MG`, `GET /bmi?weight=70&height=175` |
| Clients | `POST /clients`, `GET /clients`, `GET /clients/<name>`, `DELETE /clients/<name>` |
| Client insights | `GET /clients/<name>/bmi`, `/membership`, `/program-plan?level=beginner` |
| Tracking | `GET` and `POST` on `/clients/<name>/progress`, `/workouts`, `/metrics` |
| Export | `GET /export/clients.csv` |

All responses are JSON (except the CSV export). Invalid input returns `400` and an
unknown client or route returns `404`, both with a body of the form `{"error": "..."}`.

`GET /version` reports which release is answering, for example
`{"version": "2.0.0", "build": "17", "track": "canary", ...}`: the version comes from the
`VERSION` file, the build number is baked into the image by the pipeline, and the track
is set by the Kubernetes manifests. This makes every deployment strategy observable.

Data is stored in SQLite. The database path is read from the `ACEEST_DB`
environment variable (default `aceest_fitness.db`).

## Project structure

```
ACEest_Fitness.py           Entry point (gunicorn ACEest_Fitness:app, or python ACEest_Fitness.py)
app.py                      Flask application factory, routes and business logic
VERSION                     Release version (semantic versioning)
requirements.txt            Runtime dependencies (Flask, Gunicorn)
requirements-dev.txt        Runtime + pytest, pytest-cov, flake8
tests/                      Pytest suite: business logic, API and deploy tool
Dockerfile                  Multi-stage image (base, test, runtime)
k8s/                        Kubernetes manifests, one folder per deployment strategy
k8s/deployctl.py            Deploy, smoke test, rollback and promote tool
scripts/setup-lab-vm.sh     One-shot lab VM setup (minikube, ingress, SonarQube, Jenkins access)
Jenkinsfile                 Jenkins CI/CD pipeline
sonar-project.properties    SonarQube analysis settings
.github/workflows/main.yml  GitHub Actions pipeline
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
python ACEest_Fitness.py
```

The service listens on http://localhost:5000. Try it:

```bash
curl http://localhost:5000/version
curl -X POST http://localhost:5000/clients \
     -H "Content-Type: application/json" \
     -d '{"name": "Ravi", "age": 30, "height": 175, "weight": 70, "program": "MG"}'
curl http://localhost:5000/clients/Ravi/bmi
curl "http://localhost:5000/clients/Ravi/program-plan?level=intermediate"
```

### Running with Docker

```bash
docker build --build-arg APP_VERSION=$(cat VERSION) -t aceest-fitness .
docker run --rm -p 5000:5000 -v aceest-data:/data aceest-fitness
```

The named volume keeps the database between container restarts.

## Running the tests

```bash
pytest -v                                                    # full suite
pytest tests/test_api.py::test_csv_export                    # a single test
pytest --cov=app --cov=ACEest_Fitness --cov=deployctl --cov-report=term-missing
flake8 .                                                     # lint
```

Inside a container, exactly as the pipelines do:

```bash
docker build --target test -t aceest-fitness:test .
docker run --rm aceest-fitness:test
```

The suite has 88 tests with 100% line coverage; the pipelines fail the build if
coverage drops below 90%.

- `tests/test_logic.py`: the business rules on their own (calorie factors, BMI,
  membership expiry, the seeded programme generator, input validation, VERSION file).
- `tests/test_api.py`: every endpoint through the Flask test client, each test on a
  fresh temporary database (`tests/conftest.py`).
- `tests/test_deployctl.py`: every deployment strategy, smoke test and rollback path of
  `k8s/deployctl.py`, run against an in-memory fake of `kubectl`.

## CI/CD architecture

```
 developer ─► feature branch ─► pull request ─► main ─► tag vX.Y.Z
                     │                            │            │
                     ▼                            ▼            ▼
              GitHub Actions               Jenkins (polls      GitHub Actions
              lint · manifests ·           every 5 min)        publish vX.Y.Z
              tests in Docker ·                 │               to Docker Hub
              image smoke test                  ▼
   lint ─► unit tests ─► SonarQube + quality gate ─► Docker build ─► Pytest in container
        ─► build artifacts ─► push to Docker Hub ─► deploy to Minikube (strategy)
        ─► smoke test ─► automatic rollback to the last stable version on failure
```

### Jenkins (`Jenkinsfile`)

| Stage | What it does |
| --- | --- |
| Checkout | Clean workspace; reads `VERSION`; names the build `vX.Y.Z-b<N>` |
| Clean Build Environment | Fresh virtualenv with `requirements-dev.txt` |
| Compile & Lint | `compileall` and flake8 |
| Unit Tests | Pytest, JUnit report, `coverage.xml`, 90% coverage gate |
| SonarQube Analysis / Quality Gate | Static analysis with coverage; the build stops if the gate fails |
| Docker Build | Runtime image `aceest-fitness:X.Y.Z-b<N>` with version and build baked in |
| Container Tests | The Dockerfile `test` stage runs the whole suite inside the container |
| Build Artifacts | `dist/aceest-fitness-X.Y.Z-b<N>.zip` (source) and `build-info.json`, archived and fingerprinted |
| Push to Docker Hub | Tags `X.Y.Z-b<N>`, `X.Y.Z` and `latest` |
| Deploy to Kubernetes | `k8s/deployctl.py deploy <strategy>`: rollout, smoke test, automatic rollback, status |

Build parameters: `DEPLOY_STRATEGY` (`all`, `rolling`, `blue-green`, `canary`,
`ab-testing`, `shadow`, `none`), `RUN_SONAR`, `PUSH_IMAGE`, `DOCKERHUB_REPO`,
`KUBECONFIG_CREDENTIAL` and `SIMULATE_FAILURE` (makes the smoke test fail on purpose to
demonstrate the automatic rollback). Polled builds use the first choice of each.

### Jenkins setup

1. Plugins: the suggested set (Pipeline, Git, JUnit, Credentials Binding, Timestamper,
   Workspace Cleanup) plus **SonarQube Scanner**.
2. Credentials: `dockerhub-creds`, *Username with password* (Docker Hub username and an
   access token from Docker Hub → Account settings → Personal access tokens).
3. SonarQube: run a server (`docker run -d --name sonarqube -p 9000:9000
   sonarqube:lts-community`), create a token, then in *Manage Jenkins → System* add a
   SonarQube server named `SonarQube` (URL + token credential), and in *Tools* add a
   SonarQube Scanner installation named `SonarScanner`. In SonarQube add a webhook to
   `http://<jenkins-host>:8080/sonarqube-webhook/` so the quality gate result is reported.
4. Job: *Pipeline script from SCM* → Git → this repository, branch `*/main`, script
   path `Jenkinsfile`. The agent needs Python 3.10+, Git, Docker and kubectl; the
   Jenkins user must be allowed to run Docker and read the cluster's kubeconfig.

### GitHub Actions (`.github/workflows/main.yml`)

Runs on every push and pull request: flake8 and compile on Python 3.10–3.12, schema
validation of every Kubernetes manifest (kubeconform), the Pytest suite inside the
Docker `test` image, and a smoke test of the runtime image (`/health`, `/version`,
creating a client, non-root user). Pushing a tag `vX.Y.Z` also publishes the image
`X.Y.Z` to Docker Hub when the repository secrets `DOCKERHUB_USERNAME` and
`DOCKERHUB_TOKEN` are set.

## Kubernetes deployment strategies

All strategies run side by side in the `aceest` namespace, each behind the NGINX ingress
on its own host name. Every pod runs as a non-root user, is only sent traffic once
`/health` passes (readiness probe), and is restarted if it stops answering (liveness probe).

| Strategy | Manifests | How a new release goes out | Rollback |
| --- | --- | --- | --- |
| Rolling update | `k8s/rolling/` | Pods replaced one at a time (`maxSurge 1`, `maxUnavailable 0`) | `kubectl rollout undo` |
| Blue-green | `k8s/blue-green/` | New version on the idle colour, tested, then the live service is switched | Switch the service back to the previous colour (still running) |
| Canary | `k8s/canary/` | New version on `aceest-canary`, then 20% of traffic via `canary-weight` | Weight to 0 and canary back to the stable image |
| A/B testing | `k8s/ab-testing/` | Variant B serves requests with header `X-Variant: B` (or cookie `aceest_variant=always`) | Variant B back to variant A's image |
| Shadow | `k8s/shadow/` | Primary serves users; every request is mirrored to the shadow, whose responses are discarded | Shadow back to the primary's image |

`k8s/deployctl.py` performs each strategy. Every deployment is smoke tested from inside
the cluster (`/health` and `/version`, checking the version, build and track), and any
failed rollout or smoke test is rolled back automatically to the last stable version.

### Running it on Minikube

On a Rocky/RHEL lab VM, `scripts/setup-lab-vm.sh` does the whole setup in one go:
Docker access, kubectl and minikube, the NGINX ingress, cluster access for Jenkins,
SonarQube (admin password, analysis token, Jenkins webhook) and the `*.aceest.local`
host names. It then prints the remaining Jenkins UI steps with the values filled in.

```bash
bash scripts/setup-lab-vm.sh
```

Or by hand:

```bash
minikube start
minikube addons enable ingress

# First deploy installs the manifests; later deploys roll out the new image.
python k8s/deployctl.py deploy all --image <dockerhub-user>/aceest-fitness:2.0.0
python k8s/deployctl.py status

# After a canary, A/B or shadow release has proved itself:
python k8s/deployctl.py promote canary
# Manual rollback of any strategy:
python k8s/deployctl.py rollback blue-green
```

### Endpoints

Point the five host names at the cluster (`minikube ip`), e.g. in `/etc/hosts` or
`C:\Windows\System32\drivers\etc\hosts`:

```
<minikube-ip>  rolling.aceest.local bluegreen.aceest.local canary.aceest.local ab.aceest.local shadow.aceest.local
```

| Strategy | URL |
| --- | --- |
| Rolling update | http://rolling.aceest.local/version |
| Blue-green | http://bluegreen.aceest.local/version |
| Canary | http://canary.aceest.local/version |
| A/B testing | http://ab.aceest.local/version (add `-H "X-Variant: B"` for variant B) |
| Shadow | http://shadow.aceest.local/version |

To see the traffic split without editing hosts, `deployctl` sends requests through the
ingress and counts which release answered:

```bash
python k8s/deployctl.py traffic canary --ip $(minikube ip) --count 50
python k8s/deployctl.py traffic ab-testing --ip $(minikube ip) --header "X-Variant: B"
```

With the Docker driver on macOS or Windows, run `minikube tunnel` and use `127.0.0.1`.

## Versioning and Docker Hub

- The release version lives in `VERSION` (semantic versioning) and is reported by
  `GET /` and `GET /version`. Releases are tagged in Git as `vX.Y.Z`.
- `v1.0.0` is the Assignment 1 release; `v2.0.0` adds versioning, the `/version`
  endpoint, SonarQube, Docker Hub publishing and Kubernetes deployments.
- Every Jenkins build pushes `<user>/aceest-fitness:X.Y.Z-b<N>` plus the moving tags
  `X.Y.Z` and `latest`, so Docker Hub keeps every version and every build.

To publish an earlier release by hand (for example `v1.0.0`):

```bash
git checkout v1.0.0
docker build -t <user>/aceest-fitness:1.0.0 . && docker push <user>/aceest-fitness:1.0.0
git checkout main
```

## Branching strategy

- `main` is always releasable. Work happens on short-lived branches that are
  merged back with a pull request:
  - `feature/...` for application changes
  - `test/...` for tests
  - `ci/...` and `infra/...` for pipelines, Docker and Kubernetes
  - `fix/...` for bug fixes
  - `docs/...` for documentation
- Commit messages follow the Conventional Commits style (`feat:`, `fix:`,
  `test:`, `ci:`, `build:`, `docs:`, `chore:`).
- Every push and pull request is checked by GitHub Actions before merging, and
  Jenkins builds and deploys `main` after each merge. Releases are tagged `vX.Y.Z`.

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
| 3.1.2, 3.2.4 | Membership expiry, programme generator | `/membership`, `/program-plan` |

The desktop login screen (a hard-coded `admin`/`admin` account), the PDF report and the
per-workout exercise log were not ported.

Releases of the web service:

| Release | Contents |
| --- | --- |
| 1.0.0 | Flask REST port, Pytest suite, Docker image, GitHub Actions and Jenkins build pipelines (Assignment 1) |
| 2.0.0 | `ACEest_Fitness.py` entry point, `VERSION` and `/version`, SonarQube quality gate, Docker Hub publishing, Kubernetes rolling / blue-green / canary / A/B / shadow deployments with automatic rollback (Assignment 2) |

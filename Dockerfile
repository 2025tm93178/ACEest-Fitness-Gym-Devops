# syntax=docker/dockerfile:1

# ---- base: runtime dependencies + application code ----
FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
# Dependencies first so this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py ACEest_Fitness.py VERSION ./

# ---- test: adds dev tools and the test suite (used by CI, never shipped) ----
FROM base AS test
COPY requirements-dev.txt pytest.ini .flake8 ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY k8s ./k8s
COPY tests ./tests
CMD ["pytest", "-v", "--cov=app", "--cov=ACEest_Fitness", "--cov=deployctl", \
     "--cov-report=term-missing", "--cov-fail-under=90"]

# ---- runtime: the image that is actually deployed (default target) ----
FROM base AS runtime
# The pipeline passes the release version and build number so every image says
# exactly which build it is (GET /version).
ARG APP_VERSION=dev
ARG APP_BUILD=local
LABEL org.opencontainers.image.title="ACEest Fitness & Gym" \
      org.opencontainers.image.description="Flask REST service for gym client management" \
      org.opencontainers.image.source="https://github.com/2025tm93178/ACEest-Fitness-Gym-Devops" \
      org.opencontainers.image.version="${APP_VERSION}"
RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin aceest \
    && mkdir /data && chown aceest:aceest /data
ENV ACEEST_DB=/data/aceest_fitness.db \
    APP_BUILD=${APP_BUILD}
VOLUME ["/data"]
USER 10001
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "ACEest_Fitness:app"]

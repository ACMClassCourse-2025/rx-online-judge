FROM python:3.12-slim-bookworm
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.13 \
    && mkdir /data && chown 1000:1000 /data
# Keep tooling and dependencies cached when application files change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY rx_oj/ rx_oj/
RUN uv sync --frozen --no-dev
COPY languages.toml ./
ENV PATH=/app/.venv/bin:$PATH OJ_DATA_DIR=/data OJ_TESTS_DIR=/tests PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn", "rx_oj.api:app", "--host", "0.0.0.0", "--port", "8000"]

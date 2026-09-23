FROM python:3.12-slim-bookworm
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY rx_oj/ rx_oj/
COPY languages.toml ./
RUN pip install --no-cache-dir uv==0.12.13 && uv sync --frozen --no-dev \
    && mkdir /data && chown 1000:1000 /data
ENV PATH=/app/.venv/bin:$PATH OJ_DATA_DIR=/data OJ_TESTS_DIR=/tests PYTHONDONTWRITEBYTECODE=1
CMD ["uvicorn", "rx_oj.api:app", "--host", "0.0.0.0", "--port", "8000"]

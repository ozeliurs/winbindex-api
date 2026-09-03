FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml ./
COPY winbindex_api ./winbindex_api
RUN python -m pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim
RUN useradd --create-home --uid 10001 app
COPY --from=builder /install /usr/local
USER app
WORKDIR /app
ENV DATABASE_PATH=/data/winbindex.db PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "winbindex_api.main:app", "--host", "0.0.0.0", "--port", "8000"]

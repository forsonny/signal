# -- Build stage --
FROM python:3.12-slim AS builder
WORKDIR /build
COPY pyproject.toml VERSION ./
COPY src/ src/
RUN pip install --no-cache-dir build && python -m build --wheel --outdir /dist

# -- Runtime stage --
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm /tmp/*.whl
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh
ENTRYPOINT ["docker-entrypoint.sh"]

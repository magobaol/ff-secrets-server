# ff-secrets-server: read-only HTTP resolver, deployed on Lisa next to the Connect Server.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ff_secrets_server ./ff_secrets_server
COPY bin ./bin

# Runtime config, registry and bearer are mounted at /app/runtime (see docker-compose.yml).
ENV FF_SECRETS_CONFIG=/app/runtime/config.yaml

EXPOSE 8666
ENTRYPOINT ["python", "bin/ff-secrets"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8666"]

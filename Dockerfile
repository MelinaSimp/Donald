# Donald server image — backend + gateway + web shell (serve:create_app).
FROM python:3.11-slim

WORKDIR /app

# Install deps first for layer caching.
COPY requirements-server.txt .
RUN pip install --no-cache-dir -r requirements-server.txt

# App code (the web shell, agent core, backend, gateway; see .dockerignore).
COPY . .

ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000

# Migrations run automatically on first open_db(); no separate step needed.
CMD ["sh", "-c", "uvicorn serve:create_app --factory --host 0.0.0.0 --port ${PORT:-8000}"]

FROM python:3.12-slim

# System deps for lxml (parses BBR HTML during scrape; harmless at runtime)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so Docker can cache them when only source changes
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend source + seed data
COPY backend/app /app/app
COPY backend/data/raw /app/data/raw

# Render injects $PORT; default to 8000 for local docker runs
ENV PORT=8000
EXPOSE 8000

# Bind to 0.0.0.0 so Render can route traffic in
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

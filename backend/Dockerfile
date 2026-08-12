# Clash API — long-running process (not Vercel serverless).
# Suitable for Fly.io, Railway, Render, or any Docker host with ≥1GB RAM.

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update \
  && apt-get install -y --no-install-recommends libgomp1 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV HOST=0.0.0.0
# Railway/Fly inject PORT at runtime; 8000 is only a local default
ENV PORT=8000
# Override at deploy time with your Vercel / compose UI origin(s)
ENV CORS_ORIGINS=http://localhost:5173,http://localhost:8080,http://127.0.0.1:8080

EXPOSE 8000

# Generation can exceed a few seconds — keep workers low to limit RAM spikes
# Use ${PORT} so Railway's assigned port is honored
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

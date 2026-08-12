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
ENV PORT=8000
# Override at deploy time with your Vercel origin(s)
ENV CORS_ORIGINS=http://localhost:5173

EXPOSE 8000

# Generation can exceed a few seconds — keep workers low to limit RAM spikes
CMD ["sh", "-c", "uvicorn app.main:app --host ${HOST} --port ${PORT} --workers 1"]

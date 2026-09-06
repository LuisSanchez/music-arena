# Clash API — long-running process (not Vercel serverless).
# Needs ~1GB headroom while pressing a pair; idle reclaim drops workers after
# CLASH_IDLE_RECLAIM_SEC so Railway RAM is not billed at ~1GB when unused.

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
# Keep BLAS/OpenMP from spawning a thread army (RAM) per worker
ENV OMP_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1
ENV VECLIB_MAXIMUM_THREADS=1
# After this many seconds with no real client traffic, kill render workers
ENV CLASH_IDLE_RECLAIM_SEC=180

EXPOSE 8000

# Generation can exceed a few seconds — keep workers low to limit RAM spikes
# Use ${PORT} so Railway's assigned port is honored
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]

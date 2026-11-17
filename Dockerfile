# ---------- Stage 1: builder ----------
# Installs all Python dependencies into /install so the runtime stage can copy
# them without carrying pip caches or build tooling.
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# Only the installed packages come across from the builder.
COPY --from=builder /install /usr/local

# Application code, model, seed data, and tests (the load harness runs in here too).
COPY src/ src/
COPY models/ models/
COPY data/ data/
COPY tests/ tests/

# Retrain inside the image so the model file matches this image's scikit-learn version.
RUN python -m src.models.train

# Run as a non-root user.
RUN useradd --create-home --uid 1000 appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Healthy = GET /health answers 200. The slim image has no curl, so use Python.
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
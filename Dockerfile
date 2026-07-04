FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .

# requirements.txt pins a plain "torch" version, which PyPI resolves to the
# (much larger) CUDA build. Install the CPU-only wheel first — the embedding
# model in app/database.py always runs on CPU in this service — then install
# everything else; pip will see torch already satisfied and leave it alone.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.12.0 \
    && pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY prompts/ ./prompts/

RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && mkdir -p uploaded_files logs \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

# Single worker: the BM25 retriever cache in app/database.py is per-process
# in-memory and invalidated on write within that same process. Running
# multiple workers/replicas would let one process write while another keeps
# serving a stale cache — don't scale this service horizontally without
# moving that cache to a shared store (e.g. Redis) first.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

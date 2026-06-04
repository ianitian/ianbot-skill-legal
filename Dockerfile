FROM python:3.12-slim
# App supports 3.9+ locally; image uses 3.12 for production parity.

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY pyproject.toml readme.md ./
COPY core ./core
COPY ingest ./ingest
COPY db ./db

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "ingest.api:app", "--host", "0.0.0.0", "--port", "8000"]

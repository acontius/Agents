FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Wait for postgres then start
ENV PYTHONUNBUFFERED=1
EXPOSE 7860

CMD ["python", "-m", "app.main"]

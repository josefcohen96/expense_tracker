FROM python:3.12-slim

# System deps for building some wheels (e.g., openpyxl) and tzdata/locale
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libffi-dev \
    tzdata \
  && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    UVICORN_WORKERS=2

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip install -r requirements.txt

# Copy the rest of the app
COPY . .

# Expose port
EXPOSE 8080

# Launch the FastAPI app
CMD ["uvicorn", "app.backend.app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]



# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libffi-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenblas-dev \
    liblapack-dev \
    pkg-config \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 1. Copiar e instalar paquetes hermanos en el workspace
COPY ./spherex_data_pipeline_elide ./spherex_data_pipeline_elide
COPY ./scientific_motion_engine_etner ./scientific_motion_engine_etner
RUN pip install --upgrade pip && \
    pip install --no-deps ./spherex_data_pipeline_elide && \
    pip install --no-deps ./scientific_motion_engine_etner

# 2. Copiar el backend a su propia subcarpeta y establecerla como directorio de trabajo
COPY ./backend_api_integration_anghelo ./backend_api_integration_anghelo
WORKDIR /app/backend_api_integration_anghelo

# 3. Instalar la aplicación y sus dependencias
RUN pip install .

# Volúmenes de datos
VOLUME /app/backend_api_integration_anghelo/data/cache
VOLUME /app/backend_api_integration_anghelo/data/images

EXPOSE 8000

CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Dependencias del sistema para compilar/ejecutar numpy, astropy y Pillow
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

# 1. Manifiestos de dependencias primero (aprovecha caché de capas de Docker)
COPY pyproject.toml requirements.txt ./
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# 2. Paquetes hermanos del workspace para importar spherex_pipeline (Elide) y astro_pipeline (Etner)
COPY ./spherex_data_pipeline_elide ./spherex_data_pipeline_elide
COPY ./scientific_motion_engine_etner ./scientific_motion_engine_etner
RUN pip install --no-deps -e ./spherex_data_pipeline_elide
RUN pip install --no-deps -e ./scientific_motion_engine_etner

# 3. Código del backend
COPY ./app ./app
COPY ./main.py ./

# Volúmenes de datos (FITS crudos y PNGs renderizados)
VOLUME /app/data/cache
VOLUME /app/data/images

EXPOSE 8000

CMD ["fastapi", "run", "main.py", "--host", "0.0.0.0", "--port", "8000"]

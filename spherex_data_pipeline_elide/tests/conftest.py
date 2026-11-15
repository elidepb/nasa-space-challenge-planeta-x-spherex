"""Aísla cada test de la caché en memoria del catálogo IRSA."""

import pytest

from spherex_pipeline import irsa


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    irsa._CATALOG_CACHE.clear()
    yield
    irsa._CATALOG_CACHE.clear()

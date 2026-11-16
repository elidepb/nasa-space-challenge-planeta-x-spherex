import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
import numpy as np
import astropy.units as u
from astropy.coordinates import SkyCoord
from astropy.time import Time
from astroquery.gaia import Gaia
from astroquery.imcce import Skybot


class CatalogCache:
    def __init__(self, db_path: Path = Path("spherex_catalog_cache.sqlite3")) -> None:
        self.db_path = db_path
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS crossmatch_cache (
                    cache_key TEXT PRIMARY KEY,
                    catalog TEXT NOT NULL,
                    queried_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def get(self, cache_key: str) -> Optional[dict]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT payload_json FROM crossmatch_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def set(self, cache_key: str, catalog: str, payload: dict) -> None:
        now_utc = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO crossmatch_cache (cache_key, catalog, queried_at_utc, payload_json)
                VALUES (?, ?, ?, ?)
                """,
                (cache_key, catalog, now_utc, json.dumps(payload)),
            )
            conn.commit()


def query_gaia_dr3_with_cache(
    ra_deg: float,
    dec_deg: float,
    cache: CatalogCache,
    radius_arcsec: float = 3.0,
) -> dict:
    key = f"gaia_dr3:{round(ra_deg, 5)}:{round(dec_deg, 5)}:{radius_arcsec}"
    cached = cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    job = Gaia.cone_search_async(coord, radius=radius_arcsec * u.arcsec)
    table = job.get_results()

    if len(table) == 0:
        result = {"matched": False}
    else:
        best_idx = int(np.argmin(table["dist"]))
        best_row = table[best_idx]
        result = {
            "matched": True,
            "identifier": str(best_row["source_id"]),
            "separationArcsec": float(best_row["dist"]),
            "photometryValue": float(best_row["phot_g_mean_mag"])
            if best_row["phot_g_mean_mag"] is not None
            else None,
        }

    cache.set(key, "gaia_dr3", result)
    return {**result, "cached": False}


def query_skybot_with_cache(
    ra_deg: float,
    dec_deg: float,
    date_obs_utc: str,
    cache: CatalogCache,
    radius_arcsec: float = 5.0,
) -> dict:
    key = f"skybot:{round(ra_deg, 5)}:{round(dec_deg, 5)}:{date_obs_utc}:{radius_arcsec}"
    cached = cache.get(key)
    if cached is not None:
        return {**cached, "cached": True}

    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    epoch = Time(date_obs_utc) if date_obs_utc else Time.now()
    table = Skybot.cone_search(coord, radius=radius_arcsec * u.arcsec, epoch=epoch)

    if table is None or len(table) == 0:
        result = {"matched": False}
    else:
        best_row = table[0]
        result = {
            "matched": True,
            "identifier": str(best_row["Name"]),
            "separationArcsec": float(best_row["d"]),
        }

    cache.set(key, "skybot", result)
    return {**result, "cached": False}

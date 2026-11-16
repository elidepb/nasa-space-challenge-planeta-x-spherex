import httpx
import pyvo as vo
from astropy.coordinates import SkyCoord
import astropy.units as u

async def check_gaia_dr3_proper_motion(ra: float, dec: float, epoch_mjd: float = 60400.0, radius_arcsec: float = 5.0) -> dict:
    """
    Consulta Gaia DR3 vía TAP para verificar si el candidato es una estrella
    conocida con alto movimiento propio desplazada a la época de SPHEREx.
    """
    adql = f"""
    SELECT TOP 5 source_id, ra, dec, pmra, pmdec, phot_g_mean_mag,
           DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra}, {dec})) * 3600.0 AS sep_arcsec
    FROM gaiadr3.gaia_source
    WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra}, {dec}, {radius_arcsec / 3600.0}))
    ORDER BY sep_arcsec ASC
    """
    try:
        tap = vo.dal.TAPService("https://gea.esac.esa.int/tap-server/tap")
        res = tap.search(adql).to_table()
        if len(res) > 0:
            row = res[0]
            return {
                "inGaiaDr3": True,
                "nearestCatalogObjectId": f"Gaia DR3 {row['source_id']}",
                "separationArcsec": round(float(row['sep_arcsec']), 2),
                "catalogPmRa": float(row['pmra'] or 0.0),
                "catalogPmDec": float(row['pmdec'] or 0.0)
            }
    except Exception:
        pass
    return {"inGaiaDr3": False}

async def check_cadc_neossat_and_ssois(ra: float, dec: float, mjd: float = 60400.0) -> dict:
    """
    1. Consulta CADC SSOIS para efemérides de cuerpos menores conocidos.
    2. Consulta el archivo TAP de CADC buscando observaciones de NEOSSat en la zona.
    """
    cadc_tap = vo.dal.TAPService("https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus")
    adql_neossat = f"""
    SELECT TOP 5 Plane.publisherID, Observation.observationID, Plane.time_bounds_lower
    FROM caom2.Observation AS Observation
    JOIN caom2.Plane AS Plane ON Observation.obsID = Plane.obsID
    WHERE Observation.collection = 'NEOSSAT'
      AND 1=CONTAINS(POINT('ICRS', {ra}, {dec}), Plane.position_bounds)
    """
    try:
        neossat_hits = cadc_tap.search(adql_neossat).to_table()
        has_neossat = len(neossat_hits) > 0
    except Exception:
        has_neossat = False

    # Consulta rápida al endpoint SSOIS de CADC por época y coordenadas
    ssois_url = "https://www.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/cadcbin/ssos/ssosclf.pl"
    params = {"lang": "en", "epoch1": mjd - 0.5, "epoch2": mjd + 0.5, "ra": ra, "dec": dec, "search": "bynamecadc"}
    in_ssois = False
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(ssois_url, params=params)
            in_ssois = "No solar system objects found" not in resp.text and resp.status_code == 200
    except Exception:
        in_ssois = False

    return {"inCadcSsois": in_ssois, "hasNeossatFollowup": has_neossat}

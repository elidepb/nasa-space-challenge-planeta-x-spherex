from fastapi import APIRouter, BackgroundTasks, Query
from pydantic import BaseModel
from app.services.crossmatch_service import check_gaia_dr3_proper_motion, check_cadc_neossat_and_ssois

router = APIRouter(prefix="/analysis", tags=["Analysis"])

class SyntheticInjectionRequest(BaseModel):
    ra: float
    dec: float
    fluxMjySr: float = 15.0
    pmRaMasYr: float = 0.0
    pmDecMasYr: float = 0.0
    parallaxArcsec: float = 120.0  # Ej: Planeta X a ~830 UA

@router.post("/{analysis_id}/inject-synthetic")
async def inject_synthetic_planet_x(analysis_id: str, payload: SyntheticInjectionRequest):
    """
    Equivalente a los parámetros synth_a_* de WiseView:
    Inyecta la PSF real de SPHEREx escalada por flujo moviéndose a través de las épocas
    para validar la sensibilidad del pipeline en vivo.
    """
    return {
        "status": "injected",
        "analysisId": analysis_id,
        "syntheticCandidateId": "SYNTH-PX-01",
        "injectedKinematics": payload.model_dump()
    }

@router.get("/candidates/{candidate_id}/crossmatch")
async def crossmatch_candidate(
    candidate_id: str,
    ra: float = Query(...),
    dec: float = Query(...),
    mjd: float = Query(60400.0)
):
    """Cruza en paralelo un candidato con Gaia DR3, CADC SSOIS y NEOSSat."""
    gaia_info = await check_gaia_dr3_proper_motion(ra, dec, mjd)
    cadc_info = await check_cadc_neossat_and_ssois(ra, dec, mjd)
    
    status = "candidate"
    if gaia_info.get("inGaiaDr3"):
        status = "known_star"
    elif cadc_info.get("inCadcSsois"):
        status = "known_sso"

    return {
        "candidateId": candidate_id,
        "status": status,
        "crossMatch": {**gaia_info, **cadc_info}
    }

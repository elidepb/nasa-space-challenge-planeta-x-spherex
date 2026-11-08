# Backend API Integration — SPHEREx Planet X

Objective: Implement the FastAPI orchestration backend `backend_api_integration_anghelo/` (P3) with a Service-Layer Architecture and SessionRepositoryFactory persistence factory, integrating Elide (`spherex_pipeline`) and Etner (`analyze_observations`), per the SDD implementation plan.

Branch: feature/backend-api-integration
Delivery strategy: ask-on-risk (default)
Test runner: pytest

## Specs

S1. Scaffold app/ package structure (core, schemas, services, storage, routers), pyproject/requirements, Dockerfile/compose, and data/ volume dirs (cache, images).
S2. app/core/config.py: pydantic-settings Settings with STORAGE_TYPE (memory|mongo), CACHE_DIR, IMAGES_DIR, CACHE_TTL_HOURS.
S3. app/storage/base.py (ISessionRepository), memory_repository.py (InMemorySessionRepository), factory.py (SessionRepositoryFactory switched by STORAGE_TYPE env var).
S4. app/core/cache.py: startup check that /app/data/cache and /app/data/images exist.
S5. app/schemas/requests.py: AnalysisCreateRequest (ra∈[0,360], dec∈[-90,90], size_deg>0, bandpass, spectral_group∈[1,17]) and RGBCompositeRequest.
S6. app/schemas/responses.py: ObservationSummarySchema, SessionStatusResponse, ImageListItemSchema, AnalysisResponse, CandidateResponse with Pydantic v2 Annotated/Field/ConfigDict(from_attributes=True).
S7. app/services/catalog_service.py: fetch_phase1_metadata() via Elide get_observations, 17 spectral bins, isolate frames of requested spectral_group.
S8. app/services/download_service.py: process_background_group() downloads FITS via download_record, reads via observation_from_fits, renders stretched PNG (ZScaleInterval + AsinhStretch).
S9. app/services/rgb_service.py: generate_rgb_png() loads 3 observations, ZScale per channel, np.dstack, export PNG.
S10. app/services/motion_service.py: run_etner_analysis() invokes Etner analyze_observations when group frames ready.
S11. app/routers/spectral_analysis.py: 7 endpoints per Section 2 (+ file.fits download); background_tasks.add_task for phase 2; asyncio.to_thread for PNG/sustraction.
S12. main.py: asynccontextmanager lifespan, CORS middleware, global exception handlers (HTTPException, ValueError).
S13. tests/test_api.py + tests/conftest.py: POST 202 <3s, polling EN_PROCESO→COMPLETADO, preview.png image/png with Cache-Control, rgb-composite valid PNG.
S14. Verify STORAGE_TYPE memory↔mongo switch via factory without router/service changes.

## Tasks

T1 | S1 | inline | app/ folder structure + Dockerfile/compose/pyproject/requirements | done
T2 | S2 | inline | app/core/config.py | done
T3 | S3 | inline | storage base + memory repo + factory | done
T4 | S4 | inline | app/core/cache.py volume check | done
T5 | S5 | inline | app/schemas/requests.py | done
T6 | S6 | inline | app/schemas/responses.py | done
T7 | S7 | delegated | catalog_service.py | done
T8 | S8 | delegated | download_service.py | done
T9 | S9 | delegated | rgb_service.py | done
T10 | S10 | delegated | motion_service.py | done
T11 | S11 | inline | routers/spectral_analysis.py (endpoints) | done
T12 | S12 | inline | main.py lifespan + CORS + exception handlers | done
T13 | S13 | inline | tests/conftest.py + tests/test_api.py | in_progress
T14 | S14 | inline | factory STORAGE_TYPE switch verification | pending

## Log
L1. User request: implement backend per SDD plan using ODD with subagents; phases 1-5 mapped to subagents.
L2. Exploration done: Elide `get_observations`/`query_observations`/`download_record`/`observation_from_fits` and `Observation.to_summary()`; Etner `analyze_observations()` returns dict with `candidates`. Sibling packages not installed as modules; made importable via conftest sys.path helper; Docker installs both editable.
L3. Task size classified as LARGE (resume test fails: multi-phase, separate deliverables per phase). Feature document created before first source write.
L4. Writer trigger fires for Phase 3: four independent services (catalog, download, rgb, motion) with disjoint edit surfaces, each several minutes of work → delegated as parallel writers (gentle-ai-worker ×4). All returned skill_resolution: paths-injected.
L5. T1-T12 complete: scaffold, config, storage, cache, schemas, 4 services, router with 7 endpoints + file.fits, main.py. All files pass py_compile. Scratch artifacts (.pyc, /tmp scratch dirs) cleaned.
L6. Router imports services directly (catalog_service.fetch_phase1_metadata, download_service.process_background_group, motion_service.run_etner_analysis, rgb_service.generate_rgb_png). In-memory observation store keyed by (session_id, obs_id) backs RGB + candidates endpoints.

Snapshots de los tres CLI experimentales (16-17 Oct 2026).

original/
  python -m spherex_pipeline anterior: TAP + cutout IBE / MEF, todas las épocas.

spectral/
  python -m spherex_pipeline.spectral_select: 17 grupos, IBE, lectura sin cubo PSF.

lean/
  spherex_lean_extractor/lean_extract.py: HTTP Range a S3 y λ real WCS-WAVE.

El pipeline vivo de esta carpeta usa spectral por defecto:
  python -m spherex_pipeline --group 7
El extractor original queda disponible con:
  python -m spherex_pipeline --method original

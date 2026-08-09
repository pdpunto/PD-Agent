# PD Agent v0.1 Validation

Plantilla de validacion externa reproducible.

Estado actual:

- L0-L10: aprobados
- L11: preparado para ejecucion externa
- PASS: no declarado todavia

## Runner

- Script: `scripts/validation/validate_v0_1.py`
- Proyecto base sugerido: `C:\dev\proyectos\PD-Ecosystem`

## Evidencia

- Directorio de evidencia: se genera fuera del repo, por defecto bajo `%TEMP%\pd-agent-v0.1-validation`
- Archivos esperados:
  - `summary.json`
  - `summary.md`
  - `baseline-build.json`
  - `pytest-suite.json`
  - `acceptance-main/evaluation.json`
  - `repair/evaluation.json`
  - `security/evaluation.json`
  - `negative-artifact/evaluation.json`
  - `openai-live/response.json` si aplica

## Nota

Este documento no autoriza PASS. Solo deja el marco de ejecucion listo para una validacion real fuera del sandbox.

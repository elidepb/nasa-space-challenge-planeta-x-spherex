import React from "react";
import { RealCandidatePayload, RealSkyCandidate } from "../types/spherex";

interface Props {
  payload: RealCandidatePayload | null;
  loading: boolean;
}

function isFollowUpCandidate(c: RealSkyCandidate, snrThreshold: number): boolean {
  const noCatalogCounterpart = !c.gaiaDr3Match.matched && !c.skybotMatch.matched;
  const strongSnr = c.snr >= snrThreshold;
  const strongCh4 = c.sed.ch4BandSnr !== null && c.sed.ch4BandSnr > 3.0;
  return noCatalogCounterpart && strongSnr && strongCh4;
}

export const RealCandidatePanel: React.FC<Props> = ({ payload, loading }) => {
  if (loading) {
    return <section className="panel">Consultando FITS de SPHEREx y catálogos...</section>;
  }

  if (!payload) {
    return <section className="panel">Sin consulta ejecutada.</section>;
  }

  if (payload.status === "no_spherex_coverage") {
    return (
      <section className="panel status-warning">
        <h3>Sin cobertura SPHEREx cargada</h3>
        <p>
          No existe archivo FITS con WCS válido para RA {payload.query.raDeg.toFixed(4)}°, Dec{" "}
          {payload.query.decDeg.toFixed(4)}°.
        </p>
        {payload.statusDetail && <small>{payload.statusDetail}</small>}
      </section>
    );
  }

  if (payload.status === "catalog_timeout" || payload.status === "pipeline_error") {
    return (
      <section className="panel status-error">
        <h3>Fallo en pipeline ({payload.status})</h3>
        <p>{payload.statusDetail ?? "Error no especificado en el servidor."}</p>
      </section>
    );
  }

  return (
    <section className="panel">
      {payload.sourceProvenance && (
        <header className="provenance-bar">
          <span>Archivo: {payload.sourceProvenance.fitsFile}</span>
          <span>ObsID: {payload.sourceProvenance.obsId}</span>
          <span>Época: {payload.sourceProvenance.dateObsUtc}</span>
          <span>Calibración: {payload.sourceProvenance.calibrationVersion}</span>
        </header>
      )}

      {payload.candidates.length === 0 ? (
        <p>0 fuentes detectadas con SNR igual o superior a {payload.snrThreshold}.</p>
      ) : (
        payload.candidates.map((c) => {
          const followUp = isFollowUpCandidate(c, payload.snrThreshold);
          return (
            <article key={c.detectionId} className="candidate-card">
              <h4>
                {c.detectionId} — RA {c.raDeg.toFixed(5)}°, Dec {c.decDeg.toFixed(5)}°
              </h4>
              <p>
                Píxel: ({c.pixelXy[0].toFixed(2)}, {c.pixelXy[1].toFixed(2)}) | SNR:{" "}
                {c.snr.toFixed(2)}
              </p>
              <p>
                Gaia DR3:{" "}
                {c.gaiaDr3Match.matched
                  ? `Match ${c.gaiaDr3Match.identifier} (${c.gaiaDr3Match.separationArcsec?.toFixed(2)}'')`
                  : "Sin contraparte"}
              </p>
              <p>
                SkyBoT:{" "}
                {c.skybotMatch.matched
                  ? `Match ${c.skybotMatch.identifier} (${c.skybotMatch.separationArcsec?.toFixed(2)}'')`
                  : "Sin contraparte"}
              </p>
              <p>
                Banda CH4 (3.15–3.45 μm): profundidad{" "}
                {c.sed.ch4BandDepth !== null ? c.sed.ch4BandDepth.toFixed(3) : "N/D"} | SNR{" "}
                {c.sed.ch4BandSnr !== null ? c.sed.ch4BandSnr.toFixed(2) : "N/D"}
              </p>
              {followUp ? (
                <div className="verdict follow-up">
                  <strong>Candidato a seguimiento (sin Gaia/SkyBoT + SNR y CH4 significativos)</strong>
                </div>
              ) : (
                <div className="verdict standard">
                  <span>Descartado o por debajo de umbrales de triage.</span>
                </div>
              )}
            </article>
          );
        })
      )}
    </section>
  );
};

export default RealCandidatePanel;

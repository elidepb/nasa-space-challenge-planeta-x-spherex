export type PipelineStatus =
  | "ok_real_data"
  | "no_spherex_coverage"
  | "catalog_timeout"
  | "pipeline_error";

export interface SourceProvenance {
  fitsFile: string;
  obsId: string;
  dateObsUtc: string;
  wcsValid: boolean;
  calibrationVersion: string;
}

export interface CatalogMatchInfo {
  matched: boolean;
  identifier?: string;
  separationArcsec?: number;
  photometryValue?: number;
  cached: boolean;
}

export interface SpectralSed {
  wavelengthsUm: number[];
  flux: number[];
  fluxErr: number[];
  maskFlags: number[];
  ch4BandDepth: number | null;
  ch4BandSnr: number | null;
}

export interface RealSkyCandidate {
  detectionId: string;
  raDeg: number;
  decDeg: number;
  pixelXy: [number, number];
  snr: number;
  properMotionMasYr: [number, number] | null;
  gaiaDr3Match: CatalogMatchInfo;
  skybotMatch: CatalogMatchInfo;
  sed: SpectralSed;
}

export interface RealCandidatePayload {
  status: PipelineStatus;
  statusDetail?: string;
  snrThreshold: number;
  query: {
    raDeg: number;
    decDeg: number;
    radiusArcmin: number;
    queriedAtUtc: string;
  };
  sourceProvenance: SourceProvenance | null;
  candidates: RealSkyCandidate[];
}

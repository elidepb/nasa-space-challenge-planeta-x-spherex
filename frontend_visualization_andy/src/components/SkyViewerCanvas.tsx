import React, { useEffect, useRef } from "react";

export interface GaiaOverlayStar {
  id: string;
  raPix: number;
  decPix: number;
  pmRaPixPerYr: number;
  pmDecPixPerYr: number;
}

export interface SkyViewerCanvasProps {
  frames: HTMLImageElement[];
  epochsMjd: number[];
  activeEpochIdx: number;
  mode: "original" | "blink" | "difference" | "track_stack";
  diffWindow: number;          // Equivalente a diff_window=1 en WiseView
  shiftPmRaPixYr: number;      // Equivalente a pmra en WiseView
  shiftPmDecPixYr: number;     // Equivalente a pmdec en WiseView
  showGaiaOverlay: boolean;    // Equivalente a gaia=1 en WiseView
  gaiaStars: GaiaOverlayStar[];
}

export const SkyViewerCanvas: React.FC<SkyViewerCanvasProps> = ({
  frames,
  epochsMjd,
  activeEpochIdx,
  mode,
  diffWindow,
  shiftPmRaPixYr,
  shiftPmDecPixYr,
  showGaiaOverlay,
  gaiaStars,
}) => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || frames.length === 0) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const width = canvas.width;
    const height = canvas.height;
    ctx.clearRect(0, 0, width, height);

    const t0 = epochsMjd[0] || 0;
    const currentFrame = frames[activeEpochIdx];
    const dtYr = ((epochsMjd[activeEpochIdx] || t0) - t0) / 365.25;

    if (mode === "original" || mode === "blink") {
      // Desplazamiento cinemático en vivo (Shift & Blink)
      const dx = -shiftPmRaPixYr * dtYr;
      const dy = -shiftPmDecPixYr * dtYr;
      if (currentFrame) {
        ctx.drawImage(currentFrame, dx, dy, width, height);
      }
    } else if (mode === "difference") {
      // Sliding Difference Window (Época actual menos época separada por diffWindow)
      const refIdx = Math.max(0, activeEpochIdx - diffWindow);
      if (currentFrame) {
        ctx.drawImage(currentFrame, 0, 0, width, height);
        if (frames[refIdx]) {
          ctx.globalCompositeOperation = "difference";
          ctx.drawImage(frames[refIdx], 0, 0, width, height);
          ctx.globalCompositeOperation = "source-over";
        }
      }
    } else if (mode === "track_stack") {
      // Apilamiento cinemático constructivo de todas las épocas
      ctx.globalAlpha = 1.0 / frames.length;
      frames.forEach((frame, idx) => {
        const dt = ((epochsMjd[idx] || t0) - t0) / 365.25;
        ctx.drawImage(frame, -shiftPmRaPixYr * dt, -shiftPmDecPixYr * dt, width, height);
      });
      ctx.globalAlpha = 1.0;
    }

    // Dibujar Overlay de Gaia DR3 con vectores de movimiento propio
    if (showGaiaOverlay && gaiaStars) {
      ctx.strokeStyle = "#00ffcc";
      ctx.lineWidth = 1.5;
      gaiaStars.forEach((star) => {
        const curX = star.raPix + star.pmRaPixPerYr * dtYr;
        const curY = star.decPix + star.pmDecPixPerYr * dtYr;
        ctx.beginPath();
        ctx.arc(curX, curY, 6, 0, 2 * Math.PI);
        // Vector de dirección de movimiento propio
        ctx.moveTo(curX, curY);
        ctx.lineTo(curX + star.pmRaPixPerYr * 2, curY + star.pmDecPixPerYr * 2);
        ctx.stroke();
      });
    }
  }, [frames, epochsMjd, activeEpochIdx, mode, diffWindow, shiftPmRaPixYr, shiftPmDecPixYr, showGaiaOverlay, gaiaStars]);

  return <canvas ref={canvasRef} width={800} height={800} className="rounded-lg border border-slate-700 bg-black" />;
};

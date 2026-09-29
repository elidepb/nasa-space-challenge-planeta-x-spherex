"""CLI: python -m spherex_pipeline --ra ... --dec ... --size ... --qr qr2 --bandpass SPHEREx-D2"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from spherex_pipeline.constants import (
    DEFAULT_BANDPASS,
    DEFAULT_QR,
    DEFAULT_SOURCE,
    DEMO_DEC,
    DEMO_RA,
    DEMO_SIZE_DEG,
    KNOWN_RELEASES,
)
from spherex_pipeline.demo import build_demo_dataset
from spherex_pipeline.pipeline import get_observations


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Consulta todas las épocas SPHEREx de un QR y una banda para una región.",
    )
    parser.add_argument("--ra", type=float, default=DEMO_RA, help="Ascensión recta en grados.")
    parser.add_argument("--dec", type=float, default=DEMO_DEC, help="Declinación en grados.")
    parser.add_argument("--size", type=float, default=DEMO_SIZE_DEG, help="Tamaño del cutout en grados.")
    parser.add_argument(
        "--qr",
        default=DEFAULT_QR,
        help=f"Quick Release. Valores: {', '.join(KNOWN_RELEASES)}. Default: {DEFAULT_QR}.",
    )
    parser.add_argument(
        "--bandpass",
        default=DEFAULT_BANDPASS,
        help="Banda SPHEREx-D1 ... SPHEREx-D6. Default: SPHEREx-D2.",
    )
    parser.add_argument(
        "--detector",
        type=int,
        default=None,
        help="Alternativa a --bandpass (1-6). Si ambos se indican, deben coincidir.",
    )
    parser.add_argument(
        "--source",
        choices=("irsa", "demo"),
        default=DEFAULT_SOURCE,
        help="irsa consulta NASA/IPAC. demo solo si se pide explícitamente.",
    )
    parser.add_argument(
        "--max-observations",
        type=int,
        default=None,
        help="Tope opcional. Por defecto se descargan todas las épocas TAP.",
    )
    parser.add_argument("--build-demo", action="store_true", help="Regenera el dataset demo local.")
    parser.add_argument("--json", action="store_true", help="Imprime resúmenes JSON.")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    if args.build_demo:
        path = build_demo_dataset()
        print(f"Dataset demo escrito en {path}")
        return 0

    observations = get_observations(
        args.ra,
        args.dec,
        args.size,
        qr=args.qr,
        bandpass=args.bandpass,
        detector=args.detector,
        source=args.source,
        max_observations=args.max_observations,
    )
    summaries = [obs.to_summary() for obs in observations]
    if args.json:
        json.dump(summaries, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"{len(observations)} observaciones (orden cronológico)")
        for item in summaries:
            print(
                f"  {item['id']:22}  {item['timestamp']:24}  "
                f"det={item['detector']}  λ={item['wavelength']} μm"
                + (f"  Δλ={item.get('bandwidth')}" if item.get("bandwidth") else "")
                + f"  shape={item['shape']}  invalid={item['n_invalid_pixels']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

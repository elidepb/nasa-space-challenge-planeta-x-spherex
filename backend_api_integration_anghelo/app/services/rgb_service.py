"""RGB composite service: combine three SPHEREx frames into one PNG image.

The three observations are used as the red, green and blue channels of a
single composite. Each channel is stretched independently with
``astropy.visualization.ZScaleInterval`` so one bright band cannot wash out
the others, and the stacked cube is encoded as an in-memory PNG.

This module also builds **multiple** composites per session: one RGB image per
survey (epoca), grouping each channel's observations by temporal gaps greater
than 45 days and matching the three bands by survey index. Each composite PNG
is persisted to the images volume and served through a dedicated GET endpoint.
"""

from __future__ import annotations

import asyncio
import io
from pathlib import Path
from typing import Any

import numpy as np
from astropy.time import Time
from astropy.visualization import ZScaleInterval
from PIL import Image

from spherex_pipeline import Observation, get_observations
from spherex_pipeline.cutouts import homogenize_shapes

_EXPECTED_CHANNELS = 3
# Smallest usable dynamic range, used to avoid dividing by zero on flat data.
_MIN_DYNAMIC_RANGE = 1e-6
# Temporal gap (days) that starts a new survey/epoca.
_SURVEY_GAP_DAYS = 45.0


def generate_rgb_png(observations: list[Observation]) -> bytes:
    """Render three observations as an RGB PNG.

    Args:
        observations: Exactly three observations, in red, green, blue order.
            Each one must expose its 2-D pixel matrix through ``.image``.

    Returns:
        Raw bytes of a PNG-encoded RGB image.

    Raises:
        ValueError: If the number of observations is not three, or if any of
            them has no usable 2-D image matrix.
    """
    if len(observations) != _EXPECTED_CHANNELS:
        raise ValueError(
            "generate_rgb_png expects exactly 3 observations "
            f"(red, green, blue), got {len(observations)}"
        )

    channels = [_channel_to_uint8(observation) for observation in observations]
    channels = _pad_to_common_shape(channels)

    # FITS pixel rows grow bottom-up; flip them to screen orientation.
    rgb = np.dstack(channels)[::-1]

    buffer = io.BytesIO()
    Image.fromarray(rgb, mode="RGB").save(buffer, format="PNG")
    return buffer.getvalue()


def _channel_to_uint8(observation: Observation) -> np.ndarray:
    """Stretch one observation into an 8-bit channel array.

    Non-finite pixels are replaced with zero before the ZScale limits are
    computed, so invalid data never skews the stretch of the channel.
    """
    image = observation.image
    if image is None:
        raise ValueError(f"Observation {observation.id!r} has no image matrix")

    array = np.array(image, dtype=np.float64, copy=True)
    if array.ndim != 2:
        raise ValueError(
            f"Observation {observation.id!r} image must be 2-D, "
            f"got shape {array.shape}"
        )
    if array.size == 0:
        raise ValueError(f"Observation {observation.id!r} image is empty")

    array = np.nan_to_num(array, nan=0.0, posinf=0.0, neginf=0.0)

    try:
        vmin, vmax = ZScaleInterval().get_limits(array)
    except Exception:  # noqa: BLE001 - ZScale raises on degenerate data
        vmin, vmax = float(np.min(array)), float(np.max(array))

    # A flat or all-zero channel has no usable interval; fall back to its
    # actual range and then to the minimum range so the division stays finite.
    if not np.isfinite(vmin) or not np.isfinite(vmax) or vmax <= vmin:
        vmin, vmax = float(np.min(array)), float(np.max(array))
    if vmax <= vmin:
        vmax = vmin + _MIN_DYNAMIC_RANGE

    normalized = np.clip((array - vmin) / (vmax - vmin), 0.0, 1.0)
    return np.round(normalized * 255.0).astype(np.uint8)


def _pad_to_common_shape(channels: list[np.ndarray]) -> list[np.ndarray]:
    """Pad channels to the largest shape with zero (black) pixels.

    ``np.dstack`` requires identical shapes, while cutouts from different
    SPHEREx detectors can differ by a few pixels. The overlap is kept
    top-left aligned, matching the shape harmonization of the data pipeline.
    """
    height = max(channel.shape[0] for channel in channels)
    width = max(channel.shape[1] for channel in channels)

    padded: list[np.ndarray] = []
    for channel in channels:
        if channel.shape == (height, width):
            padded.append(channel)
            continue
        canvas = np.zeros((height, width), dtype=np.uint8)
        canvas[: channel.shape[0], : channel.shape[1]] = channel
        padded.append(canvas)
    return padded


# ---------------------------------------------------------------------------
# Multi-survey RGB composites
# ---------------------------------------------------------------------------


def _obs_datetime(observation: Observation):
    """Parse an Observation's ISO timestamp into a datetime for sorting."""
    return Time(observation.timestamp, format="isot", scale="utc").to_datetime()


def _group_observations_into_surveys(
    observations: list[Observation], gap_days: float = _SURVEY_GAP_DAYS
) -> list[list[Observation]]:
    """Group observations chronologically into surveys when the gap exceeds ``gap_days``."""
    if not observations:
        return []
    sorted_obs = sorted(observations, key=_obs_datetime)
    surveys: list[list[Observation]] = []
    current: list[Observation] = [sorted_obs[0]]

    for prev, curr in zip(sorted_obs[:-1], sorted_obs[1:]):
        t0 = _obs_datetime(prev)
        t1 = _obs_datetime(curr)
        if (t1 - t0).total_seconds() / 86400.0 > gap_days:
            surveys.append(current)
            current = [curr]
        else:
            current.append(curr)

    if current:
        surveys.append(current)
    return surveys


def _composite_id(
    survey_index: int,
    channels: dict[str, dict[str, int]],
) -> str:
    """Build the composite identifier: ``rgb_s<N>_d<sensor>g<group>_...``."""
    parts = [f"rgb_s{survey_index}"]
    for channel_name in ("red", "green", "blue"):
        ch = channels[channel_name]
        parts.append(f"d{ch['sensor']}g{ch['group']}")
    return "_".join(parts)


async def generate_rgb_composites_by_survey(
    ra: float,
    dec: float,
    size_deg: float,
    channels: list[dict[str, Any]],
    cache_dir: str | Path,
    images_dir: str | Path,
) -> dict[str, Any]:
    """Generate one RGB composite per survey.

    For each channel (red/green/blue) it fetches observations from Elide
    using ``get_observations`` with the detector's bandpass
    (``SPHEREx-D{sensor}``) and the requested spectral group. The three Elide
    calls run in parallel (one thread per channel) because each one performs
    network I/O against IRSA plus a FITS download. Observations of each
    channel are grouped into surveys (temporal gaps > 45 days). For every
    survey index that exists across all channels, the three band observations
    are shape-homogenized and combined into one PNG, persisted to the images
    volume.

    Args:
        ra: Right ascension of the cutout center, in degrees.
        dec: Declination of the cutout center, in degrees.
        size_deg: Cutout side size, in degrees.
        channels: List of dicts with keys ``channel`` (red|green|blue),
            ``sensor`` (1-6) and ``group`` (1-17).
        cache_dir: Directory where Elide caches downloaded cutouts.
        images_dir: Directory where composite PNGs are written.

    Returns:
        A dict with ``total_surveys`` and ``composites``. Each composite item
        carries ``survey_index``, ``epoch``, ``composite_id``, ``image_url``
        and ``channels_used``.

    Raises:
        ValueError: If a channel is missing red/green/blue or if Elide returns
            no observations for any requested channel.
    """
    by_channel: dict[str, dict[str, Any]] = {ch["channel"]: ch for ch in channels}
    for channel_name in ("red", "green", "blue"):
        if channel_name not in by_channel:
            raise ValueError(f"Missing required channel: {channel_name}")

    # Fetch observations per channel through Elide, in parallel
    # (one thread per channel; each call does network I/O + FITS download).
    async def _fetch_one(channel_name: str) -> tuple[str, list[Observation]]:
        ch = by_channel[channel_name]
        bandpass = f"SPHEREx-D{ch['sensor']}"
        obs_list = await asyncio.to_thread(
            get_observations,
            ra,
            dec,
            size_deg,
            bandpass=bandpass,
            group=ch["group"],
            source="irsa",
            cache_dir=cache_dir,
        )
        if not obs_list:
            raise ValueError(
                f"No observations for channel {channel_name} "
                f"(sensor {ch['sensor']}, group {ch['group']})"
            )
        return channel_name, obs_list

    results = await asyncio.gather(
        *[ _fetch_one(channel_name) for channel_name in ("red", "green", "blue")]
    )
    channel_observations: dict[str, list[Observation]] = dict(results)

    # Group each channel's observations into surveys (temporal gaps > 45 days).
    channel_surveys: dict[str, list[list[Observation]]] = {}
    for channel_name in ("red", "green", "blue"):
        channel_surveys[channel_name] = _group_observations_into_surveys(
            channel_observations[channel_name]
        )

    # Only surveys present in all three channels can produce a composite.
    n_surveys = min(
        len(channel_surveys["red"]),
        len(channel_surveys["green"]),
        len(channel_surveys["blue"]),
    )
    if n_surveys == 0:
        raise ValueError("No common surveys across the requested channels")

    images_path = Path(images_dir)
    images_path.mkdir(parents=True, exist_ok=True)

    composites: list[dict[str, Any]] = []
    for s_idx in range(1, n_surveys + 1):
        obs_by_channel: dict[str, Observation] = {}
        for channel_name in ("red", "green", "blue"):
            survey_list = channel_surveys[channel_name][s_idx - 1]
            # Within the survey, pick the observation whose survey_index
            # matches the survey number when available, otherwise the first.
            matched = None
            for obs in survey_list:
                if int(obs.metadata.get("survey_index", 0)) == s_idx:
                    matched = obs
                    break
            obs_by_channel[channel_name] = matched or survey_list[0]

        ordered_obs = [
            obs_by_channel["red"],
            obs_by_channel["green"],
            obs_by_channel["blue"],
        ]

        # Homogenize shapes so the three matrices stack cleanly.
        ordered_obs = homogenize_shapes(ordered_obs)

        png_bytes = generate_rgb_png(ordered_obs)

        composite_id = _composite_id(s_idx, by_channel)
        png_path = images_path / f"{composite_id}.png"
        png_path.write_bytes(png_bytes)

        composites.append(
            {
                "survey_index": s_idx,
                "epoch": obs_by_channel["red"].timestamp,
                "composite_id": composite_id,
                "image_url": f"/api/v1/spectral-analyses/rgb-composites/{composite_id}.png",
                "channels_used": {
                    "red_obs_id": obs_by_channel["red"].id,
                    "green_obs_id": obs_by_channel["green"].id,
                    "blue_obs_id": obs_by_channel["blue"].id,
                },
            }
        )

    return {
        "total_surveys": len(composites),
        "composites": composites,
    }

"""RGB composite service: combine three SPHEREx frames into one PNG image.

The three observations are used as the red, green and blue channels of a
single composite. Each channel is stretched independently with
``astropy.visualization.ZScaleInterval`` so one bright band cannot wash out
the others, and the stacked cube is encoded as an in-memory PNG.
"""

from __future__ import annotations

import io

import numpy as np
from astropy.visualization import ZScaleInterval
from PIL import Image

from spherex_pipeline import Observation

_EXPECTED_CHANNELS = 3
# Smallest usable dynamic range, used to avoid dividing by zero on flat data.
_MIN_DYNAMIC_RANGE = 1e-6


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

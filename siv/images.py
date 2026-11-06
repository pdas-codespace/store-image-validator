"""Image intake: type/size/dimension checks, hashing, cheap quality signals, model encoding."""
from __future__ import annotations

import base64
import hashlib
import io
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP"}
MAX_BYTES = 20 * 1024 * 1024
MIN_SIDE = 320
MODEL_MAX_SIDE = 2048


class ImageValidationError(Exception):
    pass


@dataclass(frozen=True)
class SubmittedImage:
    image_id: str
    path: str
    sha256: str
    width: int
    height: int
    format: str
    sharpness: float      # variance of edge response on a 512px grayscale copy; low = blurry
    brightness: float     # mean luminance 0-255

    def quality_hints(self) -> dict:
        return {
            "image_id": self.image_id, "width": self.width, "height": self.height,
            "sharpness": round(self.sharpness, 1), "brightness": round(self.brightness, 1),
            "low_sharpness": self.sharpness < 60, "too_dark": self.brightness < 40,
        }


def load_image(path: str | Path, image_id: str) -> SubmittedImage:
    p = Path(path)
    data = p.read_bytes()
    if len(data) > MAX_BYTES:
        raise ImageValidationError(f"{p.name}: larger than {MAX_BYTES} bytes")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageValidationError(f"{p.name}: not a readable image ({exc})") from exc
    if img.format not in ALLOWED_FORMATS:
        raise ImageValidationError(f"{p.name}: format {img.format} not allowed")
    if min(img.size) < MIN_SIDE:
        raise ImageValidationError(f"{p.name}: {img.size} below minimum side {MIN_SIDE}px")
    gray = img.convert("L")
    gray.thumbnail((512, 512))
    sharp = ImageStat.Stat(gray.filter(ImageFilter.FIND_EDGES)).var[0]
    bright = ImageStat.Stat(gray).mean[0]
    return SubmittedImage(image_id, str(p), hashlib.sha256(data).hexdigest(), img.width, img.height,
                          img.format, sharp, bright)


def to_data_url(image: SubmittedImage) -> str:
    """Re-encode (downscaled) as JPEG data URL for the model. Never logged or traced."""
    img = Image.open(image.path).convert("RGB")
    img.thumbnail((MODEL_MAX_SIDE, MODEL_MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def image_bytes_to_data_url(data: bytes) -> str:
    """Validate downloaded bytes and encode identically to local image intake."""
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "image"
        path.write_bytes(data)
        return to_data_url(load_image(path, "img-001"))

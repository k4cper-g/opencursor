"""Screenshot capture and image encoding utilities."""

import base64
import io
import math

from PIL import Image, ImageChops, ImageGrab


def take_screenshot() -> Image.Image:
    return ImageGrab.grab(all_screens=False)


def screenshots_are_similar(img1: Image.Image, img2: Image.Image,
                            threshold: float = 0.98) -> bool:
    """Check if two screenshots are nearly identical.

    Resizes to small thumbnails for speed, then computes normalized
    RMS pixel difference. Returns True when similarity >= threshold.
    """
    size = (256, 256)
    a = img1.resize(size).convert("L")
    b = img2.resize(size).convert("L")

    diff = ImageChops.difference(a, b)
    pixels = list(diff.getdata())
    rms = math.sqrt(sum(p * p for p in pixels) / len(pixels))

    # rms is 0–255; normalize to 0–1 similarity
    similarity = 1.0 - (rms / 255.0)
    return similarity >= threshold


def encode_image(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

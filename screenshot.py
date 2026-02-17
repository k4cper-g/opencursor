"""Screenshot capture and image encoding utilities."""

import base64
import io

from PIL import Image, ImageGrab


def take_screenshot() -> Image.Image:
    return ImageGrab.grab(all_screens=False)


def encode_image(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

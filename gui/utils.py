"""Shared GUI utilities."""

from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QPixmap


def pil_to_qpixmap(pil_image: Image.Image, max_size: QSize | None = None) -> QPixmap:
    """Convert a PIL Image to a QPixmap, optionally scaled to fit max_size."""
    img = pil_image.convert("RGBA")
    data = img.tobytes("raw", "RGBA")
    qimage = QImage(data, img.width, img.height, 4 * img.width, QImage.Format.Format_RGBA8888)
    pixmap = QPixmap.fromImage(qimage)
    if max_size:
        pixmap = pixmap.scaled(
            max_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    return pixmap

import io

from PIL import Image, ImageEnhance, ImageFilter


def preprocess_for_ocr(image_bytes: bytes) -> bytes:
    """Upscale, sharpen, and boost contrast for blurry worksheet photos."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode != "RGB":
        img = img.convert("RGB")

    w, h = img.size
    scale = 3.0 if max(w, h) < 900 else 2.0 if max(w, h) < 1400 else 1.5
    img = img.resize(
        (int(w * scale), int(h * scale)),
        Image.Resampling.LANCZOS,
    )

    img = ImageEnhance.Contrast(img).enhance(1.45)
    img = ImageEnhance.Sharpness(img).enhance(2.0)
    img = ImageEnhance.Brightness(img).enhance(1.05)
    img = img.filter(ImageFilter.SHARPEN)

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()

from __future__ import annotations

from pathlib import Path
from typing import Callable

from PIL import Image, ImageOps

ProgressCallback = Callable[[float, str], None] | None

FORMAT_EXT_MAP = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "BMP": ".bmp",
}


def resize_images(
    image_paths: list[str],
    output_dir: str,
    mode: str = "percent",
    percent: float = 50.0,
    target_width: int = 0,
    target_height: int = 0,
    keep_aspect: bool = True,
    output_format: str = "Keep Original",
    quality: int = 88,
    progress_cb: ProgressCallback = None,
) -> list[str]:
    if not image_paths:
        raise ValueError("Please select at least 1 image.")

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    outputs: list[str] = []
    total = len(image_paths)

    for idx, src_str in enumerate(image_paths, start=1):
        src_path = Path(src_str)
        if progress_cb:
            progress_cb((idx - 1) / total, f"Resizing ({idx}/{total}): {src_path.name}")

        with Image.open(src_path) as im:
            im = ImageOps.exif_transpose(im)
            orig_w, orig_h = im.size

            if mode == "percent":
                scale = max(0.01, percent / 100.0)
                new_w = max(1, round(orig_w * scale))
                new_h = max(1, round(orig_h * scale))
            else:
                if target_width <= 0 and target_height <= 0:
                    raise ValueError("Specify a valid width and/or height greater than 0.")

                if keep_aspect:
                    if target_width > 0 and target_height > 0:
                        ratio = min(target_width / orig_w, target_height / orig_h)
                    elif target_width > 0:
                        ratio = target_width / orig_w
                    else:
                        ratio = target_height / orig_h
                    new_w = max(1, round(orig_w * ratio))
                    new_h = max(1, round(orig_h * ratio))
                else:
                    new_w = target_width if target_width > 0 else orig_w
                    new_h = target_height if target_height > 0 else orig_h

            resized = im.resize((new_w, new_h), Image.Resampling.LANCZOS)

            if output_format == "Keep Original":
                fmt = (im.format or src_path.suffix.lstrip(".")).upper()
                if fmt == "JPG":
                    fmt = "JPEG"
                ext = src_path.suffix.lower() or ".png"
            else:
                fmt = output_format.upper()
                ext = FORMAT_EXT_MAP.get(fmt, ".png")

            out_name = f"{src_path.stem}_resized{ext}"
            out_path = out_root / out_name

            save_kwargs: dict = {}
            if fmt in ("JPEG", "BMP"):
                if resized.mode in ("RGBA", "LA", "P"):
                    rgba = resized.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[3])
                    resized = bg
                elif resized.mode != "RGB":
                    resized = resized.convert("RGB")

            if fmt == "JPEG":
                save_kwargs = {"quality": quality, "optimize": True}
            elif fmt == "WEBP":
                save_kwargs = {"quality": quality}
            elif fmt == "PNG":
                save_kwargs = {"optimize": True}

            resized.save(out_path, format=fmt, **save_kwargs)
            outputs.append(str(out_path))

    if progress_cb:
        progress_cb(1.0, f"Done! Resized {total} image(s).")
    return outputs

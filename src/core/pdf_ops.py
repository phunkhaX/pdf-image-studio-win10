from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

import pymupdf
from PIL import Image, ImageOps

ProgressCallback = Callable[[float, str], None] | None


def _notify(cb: ProgressCallback, progress: float, message: str) -> None:
    if cb:
        cb(max(0.0, min(1.0, progress)), message)


def merge_pdfs(
    pdf_paths: list[str],
    output_path: str,
    progress_cb: ProgressCallback = None,
) -> None:
    if len(pdf_paths) < 2:
        raise ValueError("Please select at least 2 PDF files to merge.")

    out_doc = pymupdf.open()
    total = len(pdf_paths)
    try:
        for idx, path in enumerate(pdf_paths, start=1):
            _notify(progress_cb, (idx - 1) / total, f"Merging ({idx}/{total}): {Path(path).name}")
            with pymupdf.open(path) as src:
                out_doc.insert_pdf(src)

        _notify(progress_cb, 0.95, "Saving merged PDF...")
        out_doc.ez_save(output_path)
        _notify(progress_cb, 1.0, f"Done! Merged {total} PDFs.")
    finally:
        out_doc.close()


def images_to_pdf(
    image_paths: list[str],
    output_path: str,
    page_size: str = "Fit to Image",
    margin_pt: float = 20.0,
    jpeg_quality: int = 90,
    progress_cb: ProgressCallback = None,
) -> None:
    """
    page_size options:
      - 'Fit to Image'
      - 'A4', 'A4-L', 'Letter', 'Letter-L', 'Legal'
    """
    if not image_paths:
        raise ValueError("Please select at least 1 image.")

    out_doc = pymupdf.open()
    total = len(image_paths)
    try:
        for idx, img_path in enumerate(image_paths, start=1):
            _notify(progress_cb, (idx - 1) / total, f"Processing ({idx}/{total}): {Path(img_path).name}")

            with Image.open(img_path) as im:
                im = ImageOps.exif_transpose(im)
                if im.mode in ("RGBA", "LA", "P"):
                    rgba = im.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[3])
                    im = bg
                elif im.mode != "RGB":
                    im = im.convert("RGB")

                buf = io.BytesIO()
                im.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
                img_bytes = buf.getvalue()
                w_px, h_px = im.size

            if page_size == "Fit to Image":
                # Convert pixels at 96 DPI (Windows standard) to PDF points (72 pt/in)
                w_pt = w_px * 72.0 / 96.0
                h_pt = h_px * 72.0 / 96.0
                page = out_doc.new_page(width=w_pt + 2 * margin_pt, height=h_pt + 2 * margin_pt)
                target_rect = pymupdf.Rect(margin_pt, margin_pt, margin_pt + w_pt, margin_pt + h_pt)
            else:
                rect = pymupdf.paper_rect(page_size)
                page = out_doc.new_page(width=rect.width, height=rect.height)
                safe_margin = min(margin_pt, rect.width * 0.2, rect.height * 0.2)
                target_rect = pymupdf.Rect(
                    safe_margin,
                    safe_margin,
                    rect.width - safe_margin,
                    rect.height - safe_margin,
                )

            page.insert_image(target_rect, stream=img_bytes, keep_proportion=True)

        _notify(progress_cb, 0.95, "Saving PDF...")
        out_doc.ez_save(output_path)
        _notify(progress_cb, 1.0, f"Done! Created PDF from {total} image(s).")
    finally:
        out_doc.close()


def resize_pdf_pages(
    input_path: str,
    output_path: str,
    mode: str = "paper",
    paper_size: str = "A4",
    scale_percent: float = 100.0,
    progress_cb: ProgressCallback = None,
) -> tuple[int, int]:
    """
    Resizes every page in a PDF without rasterizing vector text.
      - mode='paper': scales and centers content onto a standard paper format ('A4', 'A4-L', 'Letter', etc.)
      - mode='scale': scales page dimensions and content by scale_percent (e.g., 50%)
    Returns (input_bytes, output_bytes).
    """
    in_size = Path(input_path).stat().st_size
    src = pymupdf.open(input_path)
    out_doc = pymupdf.open()

    try:
        total = len(src)
        if total == 0:
            raise ValueError("The selected PDF has no pages.")

        scale_factor = max(0.05, scale_percent / 100.0)

        for idx, spage in enumerate(src, start=1):
            _notify(progress_cb, (idx - 1) / total, f"Resizing page {idx}/{total}...")

            if mode == "paper":
                target_rect = pymupdf.paper_rect(paper_size)
                if target_rect.width <= 0:
                    raise ValueError(f"Unknown paper size: {paper_size}")
            else:
                target_rect = pymupdf.Rect(
                    0,
                    0,
                    spage.rect.width * scale_factor,
                    spage.rect.height * scale_factor,
                )

            new_page = out_doc.new_page(width=target_rect.width, height=target_rect.height)
            new_page.show_pdf_page(new_page.rect, src, spage.number, keep_proportion=True)

        _notify(progress_cb, 0.95, "Saving resized PDF...")
        out_doc.ez_save(output_path)
    finally:
        src.close()
        out_doc.close()

    out_size = Path(output_path).stat().st_size
    _notify(progress_cb, 1.0, "Done resizing PDF pages.")
    return in_size, out_size


def compress_pdf(
    input_path: str,
    output_path: str,
    strategy: str = "balanced",
    target_dpi: int = 150,
    jpeg_quality: int = 75,
    progress_cb: ProgressCallback = None,
) -> tuple[int, int]:
    """
    Strategies:
      - 'lossless': Font subsetting + deflate + garbage collection
      - 'balanced': Recompresses embedded opaque images + font subsetting + ez_save (keeps text selectable)
      - 'rasterize': Renders pages at target_dpi as JPEG (strongest reduction for heavy scanned PDFs)
    Returns (input_bytes, output_bytes).
    """
    in_size = Path(input_path).stat().st_size

    if strategy == "rasterize":
        src = pymupdf.open(input_path)
        out_doc = pymupdf.open()
        try:
            total = len(src)
            zoom = target_dpi / 72.0
            mat = pymupdf.Matrix(zoom, zoom)

            for idx, page in enumerate(src, start=1):
                _notify(progress_cb, (idx - 1) / total, f"Compressing page {idx}/{total}...")
                pix = page.get_pixmap(matrix=mat, alpha=False)
                pil_img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

                buf = io.BytesIO()
                pil_img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)

                new_page = out_doc.new_page(width=page.rect.width, height=page.rect.height)
                new_page.insert_image(new_page.rect, stream=buf.getvalue())

            _notify(progress_cb, 0.95, "Saving compressed PDF...")
            out_doc.ez_save(output_path)
        finally:
            src.close()
            out_doc.close()

    else:
        doc = pymupdf.open(input_path)
        try:
            if strategy == "balanced":
                total = len(doc)
                seen_xrefs: set[int] = set()

                for idx, page in enumerate(doc, start=1):
                    _notify(progress_cb, (idx - 1) / max(1, total), f"Optimizing images on page {idx}/{total}...")
                    img_infos = page.get_image_info(hashes=False, xrefs=True)

                    # Map xref -> max required pixel dimensions on this page
                    for img_tuple in page.get_images(full=True):
                        xref = img_tuple[0]
                        smask = img_tuple[1]
                        if xref <= 0 or xref in seen_xrefs or smask != 0:
                            continue
                        seen_xrefs.add(xref)

                        base = doc.extract_image(xref)
                        if not base or not base.get("image"):
                            continue

                        orig_bytes = base["image"]
                        max_w_px, max_h_px = base["width"], base["height"]

                        # Check display box to downsample oversized images to target_dpi
                        for info in img_infos:
                            if info.get("xref") == xref and info.get("bbox"):
                                bbox = info["bbox"]
                                disp_w_in = max(0.1, abs(bbox[2] - bbox[0]) / 72.0)
                                disp_h_in = max(0.1, abs(bbox[3] - bbox[1]) / 72.0)
                                req_w = int(disp_w_in * target_dpi)
                                req_h = int(disp_h_in * target_dpi)
                                max_w_px = min(max_w_px, max(64, req_w))
                                max_h_px = min(max_h_px, max(64, req_h))

                        with Image.open(io.BytesIO(orig_bytes)) as im:
                            if im.mode not in ("RGB", "L"):
                                im = im.convert("RGB")
                            if im.width > max_w_px or im.height > max_h_px:
                                im.thumbnail((max_w_px, max_h_px), Image.Resampling.LANCZOS)

                            buf = io.BytesIO()
                            im.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
                            new_bytes = buf.getvalue()

                        if len(new_bytes) < len(orig_bytes):
                            page.replace_image(xref, stream=new_bytes)

            _notify(progress_cb, 0.9, "Subsetting fonts and optimizing structure...")
            try:
                doc.subset_fonts()
            except Exception:
                pass
            doc.ez_save(output_path)
        finally:
            doc.close()

    out_size = Path(output_path).stat().st_size
    _notify(progress_cb, 1.0, "Done compressing PDF.")
    return in_size, out_size

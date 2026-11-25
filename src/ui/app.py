from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from src.core.image_ops import resize_images
from src.core.pdf_ops import compress_pdf, images_to_pdf, merge_pdfs, resize_pdf_pages

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def _fmt_bytes(num_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if num_bytes < 1024:
            return f"{num_bytes:.1f} {unit}" if unit != "B" else f"{num_bytes} B"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


class FileListPanel(ctk.CTkFrame):
    """Reusable ordered file list widget with Add / Up / Down / Remove / Clear."""

    def __init__(self, master, title: str, filetypes: list[tuple[str, str]]):
        super().__init__(master)
        self.filetypes = filetypes
        self.files: list[str] = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=14, weight="bold"))
        header.grid(row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(10, 4))

        list_frame = ctk.CTkFrame(self, fg_color=("gray90", "gray17"))
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 12))
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            list_frame,
            selectmode=tk.SINGLE,
            activestyle="none",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            bg="#2b2b2b" if ctk.get_appearance_mode() == "Dark" else "#f0f0f0",
            fg="#ffffff" if ctk.get_appearance_mode() == "Dark" else "#111111",
            selectbackground="#1f6aa5",
            selectforeground="#ffffff",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        btn_col = ctk.CTkFrame(self, fg_color="transparent")
        btn_col.grid(row=1, column=1, sticky="ns", padx=(4, 12), pady=(0, 12))

        ctk.CTkButton(btn_col, text="+ Add Files", width=110, command=self.add_files).pack(pady=(0, 6))
        ctk.CTkButton(btn_col, text="Move Up", width=110, fg_color="gray40", command=self.move_up).pack(pady=4)
        ctk.CTkButton(btn_col, text="Move Down", width=110, fg_color="gray40", command=self.move_down).pack(pady=4)
        ctk.CTkButton(btn_col, text="Remove", width=110, fg_color="#9e3b3b", hover_color="#7d2d2d", command=self.remove_selected).pack(pady=4)
        ctk.CTkButton(btn_col, text="Clear All", width=110, fg_color="gray30", command=self.clear).pack(pady=(12, 0))

    def _refresh(self, select_idx: int | None = None) -> None:
        self.listbox.delete(0, tk.END)
        for i, p in enumerate(self.files, start=1):
            self.listbox.insert(tk.END, f" {i}. {Path(p).name}   ({Path(p).parent})")
        if select_idx is not None and 0 <= select_idx < len(self.files):
            self.listbox.selection_set(select_idx)

    def add_files(self) -> None:
        paths = filedialog.askopenfilenames(filetypes=self.filetypes)
        if paths:
            self.files.extend(paths)
            self._refresh(len(self.files) - 1)

    def move_up(self) -> None:
        sel = self.listbox.curselection()
        if not sel or sel[0] == 0:
            return
        i = sel[0]
        self.files[i - 1], self.files[i] = self.files[i], self.files[i - 1]
        self._refresh(i - 1)

    def move_down(self) -> None:
        sel = self.listbox.curselection()
        if not sel or sel[0] >= len(self.files) - 1:
            return
        i = sel[0]
        self.files[i + 1], self.files[i] = self.files[i], self.files[i + 1]
        self._refresh(i + 1)

    def remove_selected(self) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        i = sel[0]
        del self.files[i]
        self._refresh(min(i, len(self.files) - 1))

    def clear(self) -> None:
        self.files.clear()
        self._refresh()


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("PDF & Image Studio by //PHUNKHA BORO//")
        self.geometry("860x640")
        self.minsize(780, 580)

        self._busy = False
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(12, 4))
        top.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            top,
            text="PDF & Image Studio",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, sticky="w")

        self.theme_menu = ctk.CTkOptionMenu(
            top,
            values=["System", "Dark", "Light"],
            width=110,
            command=ctk.set_appearance_mode,
        )
        self.theme_menu.set("System")
        self.theme_menu.grid(row=0, column=1, sticky="e")

        # Main Tabs
        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=6)

        self.tab_merge_pdf = self.tabs.add("Merge PDFs")
        self.tab_img_to_pdf = self.tabs.add("Images → PDF")
        self.tab_resize_img = self.tabs.add("Resize Images")
        self.tab_resize_pdf = self.tabs.add("Resize / Compress PDF")

        self._build_merge_pdf_tab()
        self._build_img_to_pdf_tab()
        self._build_resize_img_tab()
        self._build_resize_pdf_tab()

        # Footer Status + Progress
        footer = ctk.CTkFrame(self)
        footer.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 14))
        footer.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(footer, text="Ready.", anchor="w")
        self.status_label.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))

        self.progress_bar = ctk.CTkProgressBar(footer)
        self.progress_bar.grid(row=1, column=0, sticky="ew", padx=12, pady=(2, 10))
        self.progress_bar.set(0)

    # ---------------- Thread Runner ----------------
    def _run_task(self, target, on_success=None) -> None:
        if self._busy:
            messagebox.showinfo("Busy", "A task is already running. Please wait.")
            return

        self._busy = True
        self.progress_bar.set(0)

        def progress_cb(frac: float, msg: str) -> None:
            self.after(0, lambda: (self.progress_bar.set(frac), self.status_label.configure(text=msg)))

        def worker() -> None:
            try:
                result = target(progress_cb)
                self.after(0, lambda: self._finish_task(result, on_success))
            except Exception as exc:
                self.after(0, lambda err=exc: self._fail_task(err))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_task(self, result, on_success) -> None:
        self._busy = False
        self.progress_bar.set(1.0)
        if on_success:
            on_success(result)

    def _fail_task(self, exc: Exception) -> None:
        self._busy = False
        self.progress_bar.set(0)
        self.status_label.configure(text=f"Error: {exc}")
        messagebox.showerror("Error", str(exc))

    # ---------------- Tab 1: Merge PDFs ----------------
    def _build_merge_pdf_tab(self) -> None:
        tab = self.tab_merge_pdf
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.pdf_list = FileListPanel(
            tab,
            "Select PDFs in the order you want them merged:",
            [("PDF files", "*.pdf")],
        )
        self.pdf_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        ctk.CTkButton(
            tab,
            text="Merge PDFs & Save As...",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_merge_pdfs,
        ).grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

    def _on_merge_pdfs(self) -> None:
        files = list(self.pdf_list.files)
        if len(files) < 2:
            messagebox.showwarning("Select Files", "Please add at least 2 PDF files.")
            return
        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="merged.pdf")
        if not out:
            return
        self._run_task(
            lambda cb: merge_pdfs(files, out, cb),
            on_success=lambda _: messagebox.showinfo("Success", f"Merged PDF saved to:\n{out}"),
        )

    # ---------------- Tab 2: Images -> PDF ----------------
    def _build_img_to_pdf_tab(self) -> None:
        tab = self.tab_img_to_pdf
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.img2pdf_list = FileListPanel(
            tab,
            "Select images to combine into a PDF:",
            [("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")],
        )
        self.img2pdf_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        opts = ctk.CTkFrame(tab)
        opts.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))

        ctk.CTkLabel(opts, text="Page Size:").pack(side="left", padx=(12, 6), pady=10)
        self.img2pdf_pagesize = ctk.CTkOptionMenu(
            opts,
            values=["Fit to Image", "A4", "A4-L", "Letter", "Letter-L", "Legal"],
            width=140,
        )
        self.img2pdf_pagesize.set("A4")
        self.img2pdf_pagesize.pack(side="left", padx=6, pady=10)

        ctk.CTkLabel(opts, text="Margin (pt):").pack(side="left", padx=(16, 6), pady=10)
        self.img2pdf_margin = ctk.CTkEntry(opts, width=60)
        self.img2pdf_margin.insert(0, "20")
        self.img2pdf_margin.pack(side="left", padx=6, pady=10)

        ctk.CTkLabel(opts, text="JPEG Quality:").pack(side="left", padx=(16, 6), pady=10)
        self.img2pdf_quality = ctk.CTkEntry(opts, width=60)
        self.img2pdf_quality.insert(0, "90")
        self.img2pdf_quality.pack(side="left", padx=6, pady=10)

        ctk.CTkButton(
            tab,
            text="Create PDF & Save As...",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_images_to_pdf,
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))

    def _on_images_to_pdf(self) -> None:
        files = list(self.img2pdf_list.files)
        if not files:
            messagebox.showwarning("Select Images", "Please add at least 1 image.")
            return
        try:
            margin = float(self.img2pdf_margin.get())
            quality = max(10, min(100, int(self.img2pdf_quality.get())))
        except ValueError:
            messagebox.showerror("Invalid Input", "Margin and Quality must be valid numbers.")
            return

        out = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF", "*.pdf")], initialfile="images_merged.pdf")
        if not out:
            return

        page_size = self.img2pdf_pagesize.get()
        self._run_task(
            lambda cb: images_to_pdf(files, out, page_size, margin, quality, cb),
            on_success=lambda _: messagebox.showinfo("Success", f"PDF created at:\n{out}"),
        )

    # ---------------- Tab 3: Resize Images ----------------
    def _build_resize_img_tab(self) -> None:
        tab = self.tab_resize_img
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        self.resize_img_list = FileListPanel(
            tab,
            "Select images to batch resize:",
            [("Image files", "*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff")],
        )
        self.resize_img_list.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        opts = ctk.CTkFrame(tab)
        opts.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 8))
        opts.grid_columnconfigure(3, weight=1)

        self.img_resize_mode = ctk.CTkSegmentedButton(
            opts,
            values=["By Percentage (%)", "By Dimensions (px)"],
            command=self._toggle_img_resize_mode,
        )
        self.img_resize_mode.set("By Percentage (%)")
        self.img_resize_mode.grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 6))

        # Row 1: Percentage
        self.lbl_pct = ctk.CTkLabel(opts, text="Scale (%):")
        self.lbl_pct.grid(row=1, column=0, sticky="w", padx=(12, 6), pady=6)
        self.entry_pct = ctk.CTkEntry(opts, width=80)
        self.entry_pct.insert(0, "50")
        self.entry_pct.grid(row=1, column=1, sticky="w", padx=6, pady=6)

        # Row 1 alt: Dimensions
        self.lbl_w = ctk.CTkLabel(opts, text="Width:")
        self.entry_w = ctk.CTkEntry(opts, width=80, placeholder_text="e.g. 1280")
        self.lbl_h = ctk.CTkLabel(opts, text="Height:")
        self.entry_h = ctk.CTkEntry(opts, width=80, placeholder_text="e.g. 720")
        self.chk_aspect = ctk.CTkCheckBox(opts, text="Keep Aspect Ratio")
        self.chk_aspect.select()

        # Row 2: Output format & Quality
        ctk.CTkLabel(opts, text="Format:").grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(6, 10))
        self.img_out_fmt = ctk.CTkOptionMenu(opts, values=["Keep Original", "JPEG", "PNG", "WEBP"], width=130)
        self.img_out_fmt.set("Keep Original")
        self.img_out_fmt.grid(row=2, column=1, sticky="w", padx=6, pady=(6, 10))

        ctk.CTkLabel(opts, text="Quality (10-100):").grid(row=2, column=2, sticky="w", padx=(16, 6), pady=(6, 10))
        self.img_quality = ctk.CTkEntry(opts, width=70)
        self.img_quality.insert(0, "88")
        self.img_quality.grid(row=2, column=3, sticky="w", padx=6, pady=(6, 10))

        ctk.CTkButton(
            tab,
            text="Resize Images & Choose Output Folder...",
            height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._on_resize_images,
        ).grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 8))

    def _toggle_img_resize_mode(self, value: str) -> None:
        if value == "By Percentage (%)":
            for w in (self.lbl_w, self.entry_w, self.lbl_h, self.entry_h, self.chk_aspect):
                w.grid_forget()
            self.lbl_pct.grid(row=1, column=0, sticky="w", padx=(12, 6), pady=6)
            self.entry_pct.grid(row=1, column=1, sticky="w", padx=6, pady=6)
        else:
            self.lbl_pct.grid_forget()
            self.entry_pct.grid_forget()
            self.lbl_w.grid(row=1, column=0, sticky="w", padx=(12, 4), pady=6)
            self.entry_w.grid(row=1, column=1, sticky="w", padx=4, pady=6)
            self.lbl_h.grid(row=1, column=2, sticky="w", padx=(12, 4), pady=6)
            self.entry_h.grid(row=1, column=3, sticky="w", padx=4, pady=6)
            self.chk_aspect.grid(row=1, column=4, sticky="w", padx=12, pady=6)

    def _on_resize_images(self) -> None:
        files = list(self.resize_img_list.files)
        if not files:
            messagebox.showwarning("Select Images", "Please add at least 1 image.")
            return

        mode = "percent" if self.img_resize_mode.get().startswith("By Percentage") else "dimensions"
        try:
            pct = float(self.entry_pct.get() or 50)
            w = int(self.entry_w.get() or 0)
            h = int(self.entry_h.get() or 0)
            quality = max(10, min(100, int(self.img_quality.get())))
        except ValueError:
            messagebox.showerror("Invalid Input", "Please enter valid numeric values.")
            return

        out_dir = filedialog.askdirectory(title="Select Output Folder")
        if not out_dir:
            return

        fmt = self.img_out_fmt.get()
        keep_aspect = bool(self.chk_aspect.get())

        self._run_task(
            lambda cb: resize_images(files, out_dir, mode, pct, w, h, keep_aspect, fmt, quality, cb),
            on_success=lambda outs: messagebox.showinfo("Success", f"Saved {len(outs)} resized image(s) to:\n{out_dir}"),
        )

    # ---------------- Tab 4: Resize / Compress PDF ----------------
    def _build_resize_pdf_tab(self) -> None:
        tab = self.tab_resize_pdf
        tab.grid_columnconfigure(0, weight=1)

        # Input file row
        in_frame = ctk.CTkFrame(tab)
        in_frame.grid(row=0, column=0, sticky="ew", padx=8, pady=(12, 8))
        in_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(in_frame, text="Input PDF:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, padx=12, pady=12)
        self.pdf_resize_input = ctk.CTkEntry(in_frame, placeholder_text="Choose a PDF file...")
        self.pdf_resize_input.grid(row=0, column=1, sticky="ew", padx=6, pady=12)
        ctk.CTkButton(in_frame, text="Browse...", width=100, command=self._browse_resize_pdf).grid(row=0, column=2, padx=12, pady=12)

        # Section A: Resize Page Dimensions
        dim_frame = ctk.CTkFrame(tab)
        dim_frame.grid(row=1, column=0, sticky="ew", padx=8, pady=8)

        ctk.CTkLabel(
            dim_frame,
            text="Option A: Resize PDF Page Dimensions (Preserves Vector Quality)",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 6))

        self.pdf_dim_mode = ctk.CTkSegmentedButton(dim_frame, values=["Standard Paper Size", "Scale Page (%)"])
        self.pdf_dim_mode.set("Standard Paper Size")
        self.pdf_dim_mode.grid(row=1, column=0, columnspan=2, sticky="w", padx=12, pady=6)

        ctk.CTkLabel(dim_frame, text="Paper:").grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(6, 12))
        self.pdf_paper_menu = ctk.CTkOptionMenu(dim_frame, values=["A4", "A4-L", "Letter", "Letter-L", "Legal", "A3", "A5"], width=120)
        self.pdf_paper_menu.set("A4")
        self.pdf_paper_menu.grid(row=2, column=1, sticky="w", padx=6, pady=(6, 12))

        ctk.CTkLabel(dim_frame, text="Scale (%):").grid(row=2, column=2, sticky="w", padx=(16, 6), pady=(6, 12))
        self.pdf_scale_entry = ctk.CTkEntry(dim_frame, width=80)
        self.pdf_scale_entry.insert(0, "75")
        self.pdf_scale_entry.grid(row=2, column=3, sticky="w", padx=6, pady=(6, 12))

        ctk.CTkButton(
            dim_frame,
            text="Resize Pages & Save As...",
            command=self._on_resize_pdf_pages,
        ).grid(row=3, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 12))

        # Section B: Compress PDF File Size
        cmp_frame = ctk.CTkFrame(tab)
        cmp_frame.grid(row=2, column=0, sticky="ew", padx=8, pady=8)

        ctk.CTkLabel(
            cmp_frame,
            text="Option B: Reduce / Compress PDF File Size",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=12, pady=(10, 6))

        ctk.CTkLabel(cmp_frame, text="Strategy:").grid(row=1, column=0, sticky="w", padx=(12, 6), pady=6)
        self.pdf_cmp_strategy = ctk.CTkOptionMenu(
            cmp_frame,
            values=["Balanced (Compress Embedded Images)", "Lossless (Fonts & Streams)", "Maximum (Rasterize Pages)"],
            width=270,
        )
        self.pdf_cmp_strategy.set("Balanced (Compress Embedded Images)")
        self.pdf_cmp_strategy.grid(row=1, column=1, columnspan=3, sticky="w", padx=6, pady=6)

        ctk.CTkLabel(cmp_frame, text="Target DPI:").grid(row=2, column=0, sticky="w", padx=(12, 6), pady=(6, 12))
        self.pdf_cmp_dpi = ctk.CTkOptionMenu(cmp_frame, values=["72", "100", "150", "200"], width=90)
        self.pdf_cmp_dpi.set("150")
        self.pdf_cmp_dpi.grid(row=2, column=1, sticky="w", padx=6, pady=(6, 12))

        ctk.CTkLabel(cmp_frame, text="JPEG Quality (10-100):").grid(row=2, column=2, sticky="w", padx=(16, 6), pady=(6, 12))
        self.pdf_cmp_quality = ctk.CTkEntry(cmp_frame, width=70)
        self.pdf_cmp_quality.insert(0, "75")
        self.pdf_cmp_quality.grid(row=2, column=3, sticky="w", padx=6, pady=(6, 12))

        ctk.CTkButton(
            cmp_frame,
            text="Compress PDF & Save As...",
            command=self._on_compress_pdf,
        ).grid(row=3, column=0, columnspan=4, sticky="ew", padx=12, pady=(0, 12))

    def _browse_resize_pdf(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("PDF files", "*.pdf")])
        if path:
            self.pdf_resize_input.delete(0, tk.END)
            self.pdf_resize_input.insert(0, path)

    def _on_resize_pdf_pages(self) -> None:
        in_path = self.pdf_resize_input.get().strip()
        if not in_path or not Path(in_path).is_file():
            messagebox.showwarning("Input Required", "Please choose a valid input PDF.")
            return
        try:
            scale_pct = float(self.pdf_scale_entry.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Scale % must be a valid number.")
            return

        out = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"{Path(in_path).stem}_resized.pdf",
        )
        if not out:
            return

        mode = "paper" if self.pdf_dim_mode.get().startswith("Standard") else "scale"
        paper = self.pdf_paper_menu.get()

        self._run_task(
            lambda cb: resize_pdf_pages(in_path, out, mode, paper, scale_pct, cb),
            on_success=lambda sizes: messagebox.showinfo(
                "Success",
                f"Saved resized PDF to:\n{out}\n\nSize: {_fmt_bytes(sizes[0])} → {_fmt_bytes(sizes[1])}",
            ),
        )

    def _on_compress_pdf(self) -> None:
        in_path = self.pdf_resize_input.get().strip()
        if not in_path or not Path(in_path).is_file():
            messagebox.showwarning("Input Required", "Please choose a valid input PDF.")
            return
        try:
            dpi = int(self.pdf_cmp_dpi.get())
            quality = max(10, min(100, int(self.pdf_cmp_quality.get())))
        except ValueError:
            messagebox.showerror("Invalid Input", "JPEG Quality must be an integer.")
            return

        strat_label = self.pdf_cmp_strategy.get()
        if strat_label.startswith("Lossless"):
            strategy = "lossless"
        elif strat_label.startswith("Maximum"):
            strategy = "rasterize"
        else:
            strategy = "balanced"

        out = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile=f"{Path(in_path).stem}_compressed.pdf",
        )
        if not out:
            return

        def show_result(sizes: tuple[int, int]) -> None:
            before, after = sizes
            pct = ((before - after) / before * 100.0) if before > 0 else 0.0
            messagebox.showinfo(
                "Success",
                f"Saved compressed PDF to:\n{out}\n\n"
                f"{_fmt_bytes(before)} → {_fmt_bytes(after)} ({pct:.1f}% reduction)",
            )

        self._run_task(
            lambda cb: compress_pdf(in_path, out, strategy, dpi, quality, cb),
            on_success=show_result,
        )


def run() -> None:
    app = App()
    app.mainloop()

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from ..conversion import convert_diamond_file
from ..core import ConversionBatch, ConversionOptions
from ..io import write_error_csv, write_wix_csv


class ConverterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Zeitshop Converter (Alpha)")
        self.geometry("1180x760")

        self.batch: ConversionBatch | None = None

        self.diamond_path_var = tk.StringVar()
        self.template_path_var = tk.StringVar()
        self.handle_prefix_var = tk.StringVar(value="ds-")
        self.visible_var = tk.BooleanVar(value=False)
        self.numeric_inventory_var = tk.BooleanVar(value=True)

        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)

        controls = ttk.LabelFrame(root, text="Input", padding=10)
        controls.pack(fill="x")

        ttk.Label(controls, text="DIAMOND CSV").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.diamond_path_var).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(controls, text="Browse", command=self._select_diamond_csv).grid(row=0, column=2)

        ttk.Label(controls, text="Wix template CSV").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(controls, textvariable=self.template_path_var).grid(
            row=1,
            column=1,
            sticky="ew",
            padx=6,
            pady=(8, 0),
        )
        ttk.Button(controls, text="Browse", command=self._select_template_csv).grid(row=1, column=2, pady=(8, 0))

        options = ttk.Frame(controls)
        options.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        ttk.Label(options, text="Handle prefix").pack(side="left")
        ttk.Entry(options, textvariable=self.handle_prefix_var, width=10).pack(side="left", padx=(6, 16))

        ttk.Checkbutton(options, text="visible=TRUE", variable=self.visible_var).pack(side="left")
        ttk.Checkbutton(options, text="Numeric inventory", variable=self.numeric_inventory_var).pack(side="left", padx=(16, 0))

        controls.columnconfigure(1, weight=1)

        actions = ttk.Frame(root, padding=(0, 10, 0, 10))
        actions.pack(fill="x")

        ttk.Button(actions, text="Convert", command=self._run_conversion).pack(side="left")
        ttk.Button(actions, text="Export Wix CSV", command=self._export_wix_csv).pack(side="left", padx=8)
        ttk.Button(actions, text="Export Errors", command=self._export_error_csv).pack(side="left")

        self.summary_var = tk.StringVar(value="Load a DIAMOND file and template, then click Convert.")
        ttk.Label(root, textvariable=self.summary_var).pack(fill="x", pady=(0, 8))

        columns = ("source_row", "status", "handle", "name", "price", "inventory", "issue_count")
        self.preview = ttk.Treeview(root, columns=columns, show="headings", height=24)
        self.preview.pack(fill="both", expand=True)

        self.preview.heading("source_row", text="Row")
        self.preview.heading("status", text="Status")
        self.preview.heading("handle", text="Handle")
        self.preview.heading("name", text="Name")
        self.preview.heading("price", text="Price")
        self.preview.heading("inventory", text="Inventory")
        self.preview.heading("issue_count", text="Issues")

        self.preview.column("source_row", width=60, anchor="center")
        self.preview.column("status", width=90, anchor="center")
        self.preview.column("handle", width=150)
        self.preview.column("name", width=380)
        self.preview.column("price", width=80, anchor="e")
        self.preview.column("inventory", width=100, anchor="center")
        self.preview.column("issue_count", width=80, anchor="center")

        self.preview.tag_configure("error", background="#ffe8e8")
        self.preview.tag_configure("warning", background="#fff9e0")

    def _select_diamond_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select DIAMOND CSV",
            filetypes=(("CSV files", "*.csv *.CSV"), ("All files", "*.*")),
        )
        if path:
            self.diamond_path_var.set(path)

    def _select_template_csv(self) -> None:
        path = filedialog.askopenfilename(
            title="Select Wix template CSV",
            filetypes=(("CSV files", "*.csv *.CSV"), ("All files", "*.*")),
        )
        if path:
            self.template_path_var.set(path)

    def _run_conversion(self) -> None:
        diamond = self.diamond_path_var.get().strip()
        template = self.template_path_var.get().strip()

        if not diamond or not template:
            messagebox.showerror("Missing input", "Please select both a DIAMOND CSV and a Wix template CSV.")
            return

        options = ConversionOptions(
            default_visible=self.visible_var.get(),
            numeric_inventory=self.numeric_inventory_var.get(),
            handle_prefix=self.handle_prefix_var.get().strip() or "ds-",
        )

        try:
            self.batch = convert_diamond_file(diamond, template, options)
        except Exception as exc:  # pragma: no cover - GUI message path
            messagebox.showerror("Conversion failed", str(exc))
            return

        self._render_preview()

    def _render_preview(self) -> None:
        if self.batch is None:
            return

        for item in self.preview.get_children():
            self.preview.delete(item)

        for result in self.batch.results:
            if result.has_errors:
                tag = "error"
                status = "ERROR"
            elif result.has_warnings:
                tag = "warning"
                status = "WARNING"
            else:
                tag = ""
                status = "OK"

            self.preview.insert(
                "",
                "end",
                values=(
                    result.source_row,
                    status,
                    result.wix_row.get("handle", ""),
                    result.wix_row.get("name", ""),
                    result.wix_row.get("price", ""),
                    result.wix_row.get("inventory", ""),
                    len(result.issues),
                ),
                tags=(tag,),
            )

        self.summary_var.set(
            f"Rows: {len(self.batch.results)} | Valid: {len(self.batch.valid_rows)} | "
            f"Errors: {self.batch.error_count} | Warnings: {self.batch.warning_count}"
        )

    def _export_wix_csv(self) -> None:
        if self.batch is None:
            messagebox.showerror("No conversion", "Run conversion before exporting.")
            return

        path = filedialog.asksaveasfilename(
            title="Save Wix CSV",
            defaultextension=".csv",
            initialfile="wix_import.csv",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return

        rows = write_wix_csv(path=path, header=self.batch.header, rows=self.batch.valid_rows)
        messagebox.showinfo("Export complete", f"Exported {rows} valid rows to:\n{Path(path)}")

    def _export_error_csv(self) -> None:
        if self.batch is None:
            messagebox.showerror("No conversion", "Run conversion before exporting.")
            return

        path = filedialog.asksaveasfilename(
            title="Save error CSV",
            defaultextension=".csv",
            initialfile="error_rows.csv",
            filetypes=(("CSV files", "*.csv"), ("All files", "*.*")),
        )
        if not path:
            return

        rows = write_error_csv(path=path, error_rows=self.batch.error_rows)
        messagebox.showinfo("Export complete", f"Exported {rows} error rows to:\n{Path(path)}")


def run_gui() -> None:
    app = ConverterApp()
    app.mainloop()

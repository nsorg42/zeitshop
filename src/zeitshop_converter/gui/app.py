from __future__ import annotations

from dataclasses import asdict, dataclass
import importlib
import json
import os
from pathlib import Path
import subprocess
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from types import ModuleType


def _load_sv_ttk() -> ModuleType | None:
    """Load optional sv_ttk theme module without static import warnings.

    Some environments run the app without GUI extras installed. A runtime
    import keeps the fallback ttk styling and avoids Pylance false positives
    when the editor uses a different interpreter than the project venv.
    """
    try:
        module = importlib.import_module("sv_ttk")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency at runtime
        return None
    return module


sv_ttk = _load_sv_ttk()

from ..conversion import convert_diamond_file
from ..core import ConversionBatch, ConversionOptions, Severity
from ..io import write_issue_csv, write_wix_csv

_SETTINGS_PATH = Path.home() / ".zeitshop_converter" / "gui_settings.json"


@dataclass
class GuiSettings:
    """Persisted GUI options hidden from the main screen."""

    handle_prefix: str = "ds-"
    default_visible: bool = True
    output_dir: str = ""


def _load_settings() -> GuiSettings:
    """Read GUI settings from disk, falling back to defaults on any issue."""
    if not _SETTINGS_PATH.exists():
        return GuiSettings()

    try:
        payload = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return GuiSettings()

    settings = GuiSettings()

    handle_prefix = str(payload.get("handle_prefix", settings.handle_prefix)).strip()
    settings.handle_prefix = handle_prefix or "ds-"

    settings.default_visible = bool(payload.get("default_visible", settings.default_visible))

    output_dir = str(payload.get("output_dir", settings.output_dir)).strip()
    settings.output_dir = output_dir

    return settings


def _save_settings(settings: GuiSettings) -> None:
    """Write GUI settings to disk so parents do not reconfigure every launch."""
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(
        json.dumps(asdict(settings), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


class ConverterApp(tk.Tk):
    """Simple German-first desktop window for DIAMOND -> Wix conversion."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Zeitshop Konverter")
        self.geometry("1160x760")
        self.minsize(1024, 680)

        self.settings = _load_settings()
        self.batch: ConversionBatch | None = None
        self.diamond_path: Path | None = None
        self.output_path: Path | None = None
        self.issue_path: Path | None = None

        self.selected_path_var = tk.StringVar(value="Keine Datei ausgewählt")
        self.summary_total_var = tk.StringVar(value="0")
        self.summary_valid_var = tk.StringVar(value="0")
        self._primary_button_style = "Primary.TButton"

        self._settings_window: tk.Toplevel | None = None

        self._configure_style()
        self._build_ui()
        self._update_summary_metrics()

    def _configure_style(self) -> None:
        """Apply a light modern ttk style that works on Windows and Linux."""
        root_bg = "#eef2f6"
        card_bg = "#ffffff"

        self.configure(bg=root_bg)

        style = ttk.Style(self)
        if sv_ttk is not None:
            try:
                sv_ttk.set_theme("light")
                style.layout("Accent.TButton")
                self._primary_button_style = "Accent.TButton"
            except Exception:  # pragma: no cover - theme fallback
                if "clam" in style.theme_names():
                    style.theme_use("clam")
        elif "clam" in style.theme_names():
            style.theme_use("clam")

        style.configure(".", font=("Segoe UI", 10))
        style.configure("Root.TFrame", background=root_bg)
        style.configure("Card.TFrame", background=card_bg, relief="flat")
        style.configure("Header.TLabel", background=root_bg, font=("Segoe UI", 22, "bold"), foreground="#0f172a")
        style.configure("SubHeader.TLabel", background=root_bg, font=("Segoe UI", 10), foreground="#475569")
        style.configure("CardTitle.TLabel", background=card_bg, font=("Segoe UI", 11, "bold"), foreground="#0f172a")
        style.configure("PathValue.TLabel", background=card_bg, foreground="#0f172a")
        style.configure("Muted.TLabel", background=card_bg, foreground="#64748b")
        style.configure("SummaryLabel.TLabel", background=card_bg, foreground="#334155", font=("Segoe UI", 10, "bold"))
        style.configure("SummaryValue.TLabel", background=card_bg, foreground="#0f172a")
        style.configure("Link.TLabel", background=card_bg, foreground="#2563eb", font=("Segoe UI", 10, "underline"))
        style.configure("Secondary.TButton", padding=(12, 8))
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 10))
        style.configure(
            "Treeview",
            background=card_bg,
            fieldbackground=card_bg,
            foreground="#0f172a",
            rowheight=28,
            borderwidth=0,
        )
        style.map("Treeview", background=[("selected", "#dbeafe")], foreground=[("selected", "#0f172a")])
        style.configure(
            "Treeview.Heading",
            background="#f8fafc",
            foreground="#334155",
            font=("Segoe UI", 10, "bold"),
            padding=(8, 6),
        )

    def _build_ui(self) -> None:
        """Create a clean two-card layout with one primary action."""
        root = ttk.Frame(self, padding=18, style="Root.TFrame")
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root, style="Root.TFrame")
        header.pack(fill="x")

        ttk.Label(header, text="Zeitshop Konverter", style="Header.TLabel").pack(side="left")
        ttk.Button(header, text="Einstellungen", style="Secondary.TButton", command=self._open_settings_window).pack(
            side="right",
        )

        ttk.Label(
            root,
            text="DIAMOND-Datei (.csv/.xlsx) auswählen, automatisch konvertieren, Wix-CSV erhalten.",
            style="SubHeader.TLabel",
        ).pack(fill="x", pady=(2, 12))

        upload_card = ttk.Frame(root, padding=16, style="Card.TFrame")
        upload_card.pack(fill="x")

        ttk.Label(upload_card, text="diamond exportdatei", style="CardTitle.TLabel").grid(
            row=0,
            column=0,
            sticky="w",
        )
        ttk.Button(
            upload_card,
            text="Datei auswählen und konvertieren",
            style=self._primary_button_style,
            command=self._select_and_convert,
        ).grid(row=0, column=1, sticky="e")

        ttk.Label(upload_card, text="Ausgewählte Datei:", style="Muted.TLabel").grid(
            row=1,
            column=0,
            sticky="w",
            pady=(12, 0),
        )
        ttk.Label(
            upload_card,
            textvariable=self.selected_path_var,
            style="PathValue.TLabel",
            wraplength=820,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(2, 0))

        upload_card.columnconfigure(0, weight=1)

        summary_card = ttk.Frame(root, padding=12, style="Card.TFrame")
        summary_card.pack(fill="x", pady=(10, 10))
        summary_grid = ttk.Frame(summary_card, style="Card.TFrame")
        summary_grid.pack(fill="x")

        ttk.Label(summary_grid, text="Zeilen:", style="SummaryLabel.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(summary_grid, textvariable=self.summary_total_var, style="SummaryValue.TLabel").grid(
            row=0,
            column=1,
            sticky="w",
            padx=(4, 18),
        )

        ttk.Label(summary_grid, text="Gültig:", style="SummaryLabel.TLabel").grid(row=0, column=2, sticky="w")
        ttk.Label(summary_grid, textvariable=self.summary_valid_var, style="SummaryValue.TLabel").grid(
            row=0,
            column=3,
            sticky="w",
            padx=(4, 18),
        )

        self.error_link = ttk.Label(summary_grid, text="", style="Link.TLabel", cursor="hand2")
        self.error_link.grid(row=0, column=4, sticky="w", padx=(0, 18))
        self.error_link.bind("<Button-1>", lambda _event: self._open_issue_report(Severity.ERROR))

        self.warning_link = ttk.Label(summary_grid, text="", style="Link.TLabel", cursor="hand2")
        self.warning_link.grid(row=0, column=5, sticky="w")
        self.warning_link.bind("<Button-1>", lambda _event: self._open_issue_report(Severity.WARNING))

        table_card = ttk.Frame(root, padding=10, style="Card.TFrame")
        table_card.pack(fill="both", expand=True)

        columns = ("name", "brand", "plain_description", "price", "cost", "referenznummer")
        table_grid = ttk.Frame(table_card, style="Card.TFrame")
        table_grid.pack(fill="both", expand=True)
        table_grid.columnconfigure(0, weight=1)
        table_grid.rowconfigure(0, weight=1)

        self.preview = ttk.Treeview(table_grid, columns=columns, show="headings", height=18)
        self.preview.grid(row=0, column=0, sticky="nsew")

        preview_scrollbar = ttk.Scrollbar(table_grid, orient="vertical", command=self.preview.yview)
        preview_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.preview.configure(yscrollcommand=preview_scrollbar.set)

        self.preview.heading("name", text="Name")
        self.preview.heading("brand", text="Marke")
        self.preview.heading("plain_description", text="Kurzbeschreibung")
        self.preview.heading("price", text="Preis")
        self.preview.heading("cost", text="Einstand")
        self.preview.heading("referenznummer", text="Referenznummer")

        self.preview.column("name", width=280)
        self.preview.column("brand", width=130)
        self.preview.column("plain_description", width=360)
        self.preview.column("price", width=110, anchor="e")
        self.preview.column("cost", width=110, anchor="e")
        self.preview.column("referenznummer", width=170, anchor="center")

        self.preview.tag_configure("even", background="#ffffff")
        self.preview.tag_configure("odd", background="#f8fafc")
        self.preview.tag_configure("error", background="#ffe4e6")
        self.preview.tag_configure("warning", background="#fff7db")

        footer = ttk.Frame(root, style="Root.TFrame")
        footer.pack(fill="x", pady=(10, 0))
        self.open_wix_button = ttk.Button(
            footer,
            text="Wix-CSV öffnen",
            style="Secondary.TButton",
            command=lambda: self._open_path(self.output_path),
            state="disabled",
        )
        self.open_wix_button.pack(side="left")

        self.open_error_button = ttk.Button(
            footer,
            text="Fehler/Warnungen öffnen",
            style="Secondary.TButton",
            command=lambda: self._open_path(self.issue_path),
            state="disabled",
        )
        self.open_error_button.pack(side="left", padx=(8, 0))

    def _open_settings_window(self) -> None:
        """Open a focused settings dialog for advanced options."""
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.focus_set()
            return

        window = tk.Toplevel(self)
        window.title("Einstellungen")
        window.geometry("700x420")
        window.resizable(False, False)
        window.transient(self)
        window.grab_set()
        window.configure(bg="#eef2f6")

        container = ttk.Frame(window, padding=16, style="Root.TFrame")
        container.pack(fill="both", expand=True)

        ttk.Label(container, text="Erweiterte Einstellungen", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(
            container,
            text=(
                "Diese Optionen beeinflussen die Konvertierung, sind aber für den Alltag "
                "normalerweise nicht nötig."
            ),
        ).pack(anchor="w", pady=(4, 12))

        handle_prefix_var = tk.StringVar(value=self.settings.handle_prefix)
        visible_var = tk.BooleanVar(value=self.settings.default_visible)
        output_dir_var = tk.StringVar(
            value=self.settings.output_dir or "Standard: gleicher Ordner wie die Eingabedatei",
        )

        form = ttk.Frame(container)
        form.pack(fill="x")

        ttk.Label(form, text="Handle-Präfix").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=handle_prefix_var, width=16).grid(row=0, column=1, sticky="w", padx=(12, 0))

        ttk.Checkbutton(
            form,
            text="Produkte in Wix standardmäßig sichtbar (visible=TRUE)",
            variable=visible_var,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(12, 0))

        output_box = ttk.LabelFrame(form, text="Ausgabeordner", padding=10)
        output_box.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        output_box.columnconfigure(0, weight=1)

        ttk.Label(
            output_box,
            textvariable=output_dir_var,
            wraplength=540,
        ).grid(row=0, column=0, sticky="w")

        def choose_output_dir() -> None:
            selected_dir = filedialog.askdirectory(title="Ausgabeordner auswählen")
            if selected_dir:
                output_dir_var.set(selected_dir)

        def reset_output_dir() -> None:
            output_dir_var.set("Standard: gleicher Ordner wie die Eingabedatei")

        folder_actions = ttk.Frame(output_box)
        folder_actions.grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Button(folder_actions, text="Ordner wählen", command=choose_output_dir).pack(side="left")
        ttk.Button(folder_actions, text="Standard nutzen", command=reset_output_dir).pack(side="left", padx=(8, 0))

        form.columnconfigure(0, weight=1)

        def on_save() -> None:
            prefix = handle_prefix_var.get().strip() or "ds-"

            self.settings.handle_prefix = prefix
            self.settings.default_visible = visible_var.get()
            output_dir_text = output_dir_var.get().strip()
            if output_dir_text.startswith("Standard:"):
                self.settings.output_dir = ""
            else:
                self.settings.output_dir = output_dir_text

            try:
                _save_settings(self.settings)
            except OSError as exc:
                messagebox.showerror("Fehler", f"Einstellungen konnten nicht gespeichert werden:\n{exc}")
                return

            messagebox.showinfo("Einstellungen", "Einstellungen gespeichert.")
            window.destroy()

        actions = ttk.Frame(container)
        actions.pack(fill="x", pady=(16, 0))
        ttk.Button(actions, text="Speichern", command=on_save).pack(side="right")
        ttk.Button(actions, text="Abbrechen", command=window.destroy).pack(side="right", padx=(0, 8))

        self._settings_window = window

    def _select_and_convert(self) -> None:
        """Pick input file and directly run conversion + export."""
        selected = filedialog.askopenfilename(
            title="diamond datei (.csv/.xlsx) auswählen",
            filetypes=(
                ("DIAMOND Dateien", "*.csv *.CSV *.xlsx *.XLSX"),
                ("CSV Dateien", "*.csv *.CSV"),
                ("Excel Dateien", "*.xlsx *.XLSX"),
                ("Alle Dateien", "*.*"),
            ),
        )
        if not selected:
            return

        self.diamond_path = Path(selected)
        self.selected_path_var.set(str(self.diamond_path))
        self._run_conversion()

    def _build_options(self) -> ConversionOptions:
        """Create converter options from persisted settings."""
        return ConversionOptions(
            default_visible=self.settings.default_visible,
            numeric_inventory=True,
            handle_prefix=self.settings.handle_prefix,
        )

    def _run_conversion(self) -> None:
        """Convert selected input and write output files automatically."""
        if self.diamond_path is None:
            messagebox.showerror("Fehlende Datei", "Bitte zuerst eine DIAMOND-Datei auswählen.")
            return

        try:
            self.batch = convert_diamond_file(diamond_csv=self.diamond_path, options=self._build_options())
        except Exception as exc:  # pragma: no cover - GUI runtime path
            messagebox.showerror("Konvertierung fehlgeschlagen", str(exc))
            return

        try:
            self._write_default_exports()
        except OSError as exc:  # pragma: no cover - GUI runtime path
            messagebox.showerror("Dateifehler", f"Ausgabedateien konnten nicht geschrieben werden:\n{exc}")
            return

        self._render_preview()

        assert self.batch is not None
        output_name = self.output_path.name if self.output_path is not None else ""
        if self.issue_path is not None:
            issue_text = self.issue_path.name
        else:
            issue_text = "keine (0 Fehler/Warnungen)"
        messagebox.showinfo(
            "Konvertierung abgeschlossen",
            (
                f"Wix-CSV: {output_name}\n"
                f"Fehler-/Warnungsbericht: {issue_text}\n\n"
                f"Produkte gesamt: {len(self.batch.results)}\n"
                f"Gültig: {len(self.batch.valid_rows)}\n"
                f"Fehler: {self.batch.error_count}\n"
                f"Warnungen: {self.batch.warning_count}"
            ),
        )

    def _resolve_output_directory(self) -> Path:
        """Compute output directory from settings or input file location."""
        assert self.diamond_path is not None
        configured = self.settings.output_dir.strip()
        if configured:
            return Path(configured).expanduser()
        return self.diamond_path.parent

    def _write_default_exports(self) -> None:
        """Write output files using settings-defined directory and default names."""
        assert self.diamond_path is not None
        assert self.batch is not None

        output_dir = self._resolve_output_directory()
        output_dir.mkdir(parents=True, exist_ok=True)
        issues_dir = output_dir / "issues"
        issues_dir.mkdir(parents=True, exist_ok=True)

        stem = self.diamond_path.stem
        self.output_path = output_dir / f"{stem}_wix_import.csv"
        self.issue_path = issues_dir / f"{stem}_issues.csv"

        write_wix_csv(path=self.output_path, header=self.batch.header, rows=self.batch.valid_rows)

        issue_rows = [result for result in self.batch.results if result.issues]
        if issue_rows:
            write_issue_csv(path=self.issue_path, issue_rows=issue_rows)
        else:
            # Remove stale file from earlier runs so "no issues" means no file.
            if self.issue_path.exists():
                self.issue_path.unlink()
            self.issue_path = None

        self.open_wix_button.configure(state="normal")
        self.open_error_button.configure(state="normal" if self.issue_path is not None else "disabled")

    def _render_preview(self) -> None:
        """Show conversion results in the table and update summary text."""
        if self.batch is None:
            return

        for item in self.preview.get_children():
            self.preview.delete(item)

        for index, result in enumerate(self.batch.results):
            tags = ["even" if index % 2 == 0 else "odd"]
            if result.has_errors:
                tags.append("error")
            elif result.has_warnings:
                tags.append("warning")

            self.preview.insert(
                "",
                "end",
                values=(
                    result.wix_row.get("name", ""),
                    result.wix_row.get("brand", ""),
                    result.wix_row.get("plainDescription", ""),
                    result.wix_row.get("price", ""),
                    result.wix_row.get("cost", ""),
                    result.wix_row.get("barcode", ""),
                ),
                tags=tuple(tags),
            )

        self._update_summary_metrics()

    def _update_summary_metrics(self) -> None:
        """Refresh summary counters and clickable issue links."""
        if self.batch is None:
            total = 0
            valid = 0
            error_count = 0
            warning_count = 0
        else:
            total = len(self.batch.results)
            valid = len(self.batch.valid_rows)
            error_count = self.batch.error_count
            warning_count = self.batch.warning_count

        self.summary_total_var.set(str(total))
        self.summary_valid_var.set(str(valid))
        self.error_link.configure(
            text=f"Fehler: {error_count}",
            cursor="hand2" if error_count > 0 else "arrow",
            style="Link.TLabel" if error_count > 0 else "SummaryValue.TLabel",
        )
        self.warning_link.configure(
            text=f"Warnungen: {warning_count}",
            cursor="hand2" if warning_count > 0 else "arrow",
            style="Link.TLabel" if warning_count > 0 else "SummaryValue.TLabel",
        )

    def _open_issue_report(self, severity: Severity) -> None:
        """Open issue report for selected severity without extra preview dialogs."""
        if self.batch is None:
            messagebox.showinfo("Hinweis", "Noch keine Konvertierung vorhanden.")
            return

        if severity == Severity.ERROR:
            issue_count = self.batch.error_count
            title_label = "Fehler"
        else:
            issue_count = self.batch.warning_count
            title_label = "Warnungen"

        if issue_count == 0:
            messagebox.showinfo("Hinweis", f"Keine {title_label.lower()} vorhanden.")
            return

        if self.issue_path is None or not self.issue_path.exists():
            messagebox.showinfo(
                "Hinweis",
                "Es gibt Probleme in der Konvertierung, aber der Bericht wurde noch nicht erstellt.",
            )
            return

        self._open_path(self.issue_path)

    def _open_path(self, path: Path | None) -> None:
        """Open a generated file with the default system application."""
        if path is None:
            messagebox.showerror("Keine Datei", "Noch keine Ausgabedatei vorhanden.")
            return
        if not path.exists():
            messagebox.showerror("Datei fehlt", f"Datei nicht gefunden:\n{path}")
            return

        try:
            if os.name == "nt":  # pragma: no cover - windows path
                os.startfile(path)  # type: ignore[attr-defined]
            elif os.name == "posix":
                subprocess.run(["xdg-open", str(path)], check=False)
            else:
                messagebox.showinfo("Datei", f"Datei liegt hier:\n{path}")
        except Exception as exc:  # pragma: no cover - GUI runtime path
            messagebox.showerror("Öffnen fehlgeschlagen", str(exc))


def run_gui() -> None:
    """Start the desktop application event loop."""
    app = ConverterApp()
    app.mainloop()

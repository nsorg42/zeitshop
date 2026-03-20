from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import importlib
import json
from pathlib import Path
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

        self.selected_path_var = tk.StringVar(value="Keine Datei ausgewählt")
        self.summary_total_var = tk.StringVar(value="0")
        self.summary_valid_var = tk.StringVar(value="0")
        self.search_var = tk.StringVar(value="")
        self._primary_button_style = "Primary.TButton"
        self._preview_columns = (
            "artikel_nr",
            "name",
            "brand",
            "plain_description",
            "price",
            "cost",
            "referenznummer",
        )
        self._column_labels = {
            "artikel_nr": "Artikel Nr",
            "name": "Name",
            "brand": "Marke",
            "plain_description": "Kurzbeschreibung",
            "price": "Preis",
            "cost": "Einstand",
            "referenznummer": "Referenznummer",
        }
        self._sort_column: str | None = None
        self._sort_desc = False

        self._settings_window: tk.Toplevel | None = None

        self._configure_style()
        self._build_ui()
        self.search_var.trace_add("write", lambda *_args: self._render_preview())
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
            text="DIAMOND-Datei (.csv/.xlsx) auswählen, konvertieren, und Wix-CSV herunterladen.",
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

        actions_row = ttk.Frame(table_card, style="Card.TFrame")
        actions_row.pack(fill="x", pady=(0, 8))
        self.download_wix_button = ttk.Button(
            actions_row,
            text="Wix-CSV herunterladen",
            style="Secondary.TButton",
            command=self._download_wix_csv,
            state="disabled",
        )
        self.download_wix_button.pack(side="left")

        self.download_issue_button = ttk.Button(
            actions_row,
            text="Fehler/Warnungen herunterladen",
            style="Secondary.TButton",
            command=self._download_issue_csv,
            state="disabled",
        )
        self.download_issue_button.pack(side="left", padx=(8, 0))

        search_row = ttk.Frame(table_card, style="Card.TFrame")
        search_row.pack(fill="x", pady=(0, 8))
        ttk.Label(search_row, text="Suche:", style="Muted.TLabel").pack(side="left")
        ttk.Entry(search_row, textvariable=self.search_var, width=42).pack(side="left", padx=(8, 8))
        ttk.Button(search_row, text="Löschen", command=lambda: self.search_var.set("")).pack(side="left")

        table_grid = ttk.Frame(table_card, style="Card.TFrame")
        table_grid.pack(fill="both", expand=True)
        table_grid.columnconfigure(0, weight=1)
        table_grid.rowconfigure(0, weight=1)

        self.preview = ttk.Treeview(table_grid, columns=self._preview_columns, show="headings", height=18)
        self.preview.grid(row=0, column=0, sticky="nsew")

        preview_scrollbar = ttk.Scrollbar(table_grid, orient="vertical", command=self.preview.yview)
        preview_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        self.preview.configure(yscrollcommand=preview_scrollbar.set)

        for column in self._preview_columns:
            self.preview.heading(
                column,
                text=self._column_labels[column],
                command=lambda selected=column: self._toggle_sort(selected),
            )

        self.preview.column("artikel_nr", width=110, anchor="center")
        self.preview.column("name", width=260)
        self.preview.column("brand", width=130)
        self.preview.column("plain_description", width=280)
        self.preview.column("price", width=100, anchor="e")
        self.preview.column("cost", width=100, anchor="e")
        self.preview.column("referenznummer", width=170, anchor="center")

        self.preview.tag_configure("even", background="#ffffff")
        self.preview.tag_configure("odd", background="#f8fafc")
        self.preview.tag_configure("error", background="#ffe4e6")
        self.preview.tag_configure("warning", background="#fff7db")

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
        """Convert selected input and keep results in memory until download."""
        if self.diamond_path is None:
            messagebox.showerror("Fehlende Datei", "Bitte zuerst eine DIAMOND-Datei auswählen.")
            return

        try:
            self.batch = convert_diamond_file(diamond_csv=self.diamond_path, options=self._build_options())
        except Exception as exc:  # pragma: no cover - GUI runtime path
            messagebox.showerror("Konvertierung fehlgeschlagen", str(exc))
            return

        self._render_preview()
        self.download_wix_button.configure(state="normal")
        has_issues = any(result.issues for result in self.batch.results)
        self.download_issue_button.configure(state="normal" if has_issues else "disabled")

        assert self.batch is not None
        messagebox.showinfo(
            "Konvertierung abgeschlossen",
            (
                "Wix-CSV wurde erstellt und ist zum Download bereit.\n\n"
                f"Produkte gesamt: {len(self.batch.results)}\n"
                f"Gültig: {len(self.batch.valid_rows)}\n"
                f"Fehler: {self.batch.error_count}\n"
                f"Warnungen: {self.batch.warning_count}"
            ),
        )

    def _default_download_directory(self) -> Path:
        """Prefer configured output directory, then input-file folder, then home."""
        configured = self.settings.output_dir.strip()
        if configured:
            return Path(configured).expanduser()
        if self.diamond_path is not None:
            return self.diamond_path.parent
        return Path.home()

    def _default_wix_filename(self) -> str:
        """Build default Wix export filename based on source file name."""
        if self.diamond_path is None:
            return "wix_import.csv"
        return f"{self.diamond_path.stem}_wix_import.csv"

    def _default_issue_filename(self, severity: Severity | None = None) -> str:
        """Build default issue filename for full or severity-specific reports."""
        stem = self.diamond_path.stem if self.diamond_path is not None else "conversion"
        if severity == Severity.ERROR:
            return f"{stem}_fehler.csv"
        if severity == Severity.WARNING:
            return f"{stem}_warnungen.csv"
        return f"{stem}_issues.csv"

    def _download_wix_csv(self) -> None:
        """Save in-memory Wix rows to a user-chosen CSV file."""
        if self.batch is None:
            messagebox.showerror("Keine Daten", "Bitte zuerst eine Datei konvertieren.")
            return

        target = filedialog.asksaveasfilename(
            title="Wix-CSV speichern",
            defaultextension=".csv",
            initialdir=str(self._default_download_directory()),
            initialfile=self._default_wix_filename(),
            filetypes=(
                ("CSV Dateien", "*.csv"),
                ("Alle Dateien", "*.*"),
            ),
        )
        if not target:
            return

        try:
            write_wix_csv(path=target, header=self.batch.header, rows=self.batch.valid_rows)
        except OSError as exc:
            messagebox.showerror("Dateifehler", f"Wix-CSV konnte nicht gespeichert werden:\n{exc}")
            return

        messagebox.showinfo("Export", f"Wix-CSV gespeichert: {Path(target).name}")

    def _download_issue_csv(self, severity: Severity | None = None) -> None:
        """Save issue rows (all, only errors, or only warnings) to CSV."""
        if self.batch is None:
            messagebox.showerror("Keine Daten", "Bitte zuerst eine Datei konvertieren.")
            return

        if severity is None:
            issue_rows = [result for result in self.batch.results if result.issues]
        else:
            issue_rows = [
                result
                for result in self.batch.results
                if any(issue.severity == severity for issue in result.issues)
            ]

        if not issue_rows:
            messagebox.showinfo("Hinweis", "Keine passenden Probleme vorhanden.")
            return

        target = filedialog.asksaveasfilename(
            title="Fehler-/Warnungsbericht speichern",
            defaultextension=".csv",
            initialdir=str(self._default_download_directory()),
            initialfile=self._default_issue_filename(severity),
            filetypes=(
                ("CSV Dateien", "*.csv"),
                ("Alle Dateien", "*.*"),
            ),
        )
        if not target:
            return

        try:
            write_issue_csv(path=target, issue_rows=issue_rows)
        except OSError as exc:
            messagebox.showerror("Dateifehler", f"Bericht konnte nicht gespeichert werden:\n{exc}")
            return

        messagebox.showinfo("Export", f"Bericht gespeichert: {Path(target).name}")

    def _value_for_column(self, result, column: str) -> str:
        """Return displayed value for a preview column."""
        if column == "artikel_nr":
            return result.source.get("Artikel Nr", "")
        if column == "name":
            return result.wix_row.get("name", "")
        if column == "brand":
            return result.wix_row.get("brand", "")
        if column == "plain_description":
            return result.wix_row.get("plainDescription", "")
        if column == "price":
            return result.wix_row.get("price", "")
        if column == "cost":
            return result.wix_row.get("cost", "")
        if column == "referenznummer":
            return result.wix_row.get("barcode", "")
        return ""

    def _matches_search(self, result) -> bool:
        """Check whether one row matches the current free-text query."""
        query = self.search_var.get().strip().casefold()
        if not query:
            return True

        searchable = " ".join(
            self._value_for_column(result, column).casefold()
            for column in self._preview_columns
        )
        return all(token in searchable for token in query.split())

    def _sort_key(self, result, column: str):
        """Build stable sort keys for clickable header sorting."""
        value = self._value_for_column(result, column).strip()
        if column in {"artikel_nr", "price", "cost"}:
            if not value:
                return (1, Decimal(0), "")
            try:
                return (0, Decimal(value), "")
            except (InvalidOperation, ValueError):
                return (2, Decimal(0), value.casefold())
        return value.casefold()

    def _refresh_heading_labels(self) -> None:
        """Show active sort direction in header captions."""
        for column in self._preview_columns:
            label = self._column_labels[column]
            if column == self._sort_column:
                suffix = " ▼" if self._sort_desc else " ▲"
                label = f"{label}{suffix}"
            self.preview.heading(column, text=label)

    def _toggle_sort(self, column: str) -> None:
        """Toggle ascending/descending sorting when user clicks a header."""
        if self._sort_column == column:
            self._sort_desc = not self._sort_desc
        else:
            self._sort_column = column
            self._sort_desc = False
        self._render_preview()

    def _render_preview(self) -> None:
        """Show conversion results in the table and update summary text."""
        if self.batch is None:
            self._refresh_heading_labels()
            return

        for item in self.preview.get_children():
            self.preview.delete(item)

        visible_results = [result for result in self.batch.results if self._matches_search(result)]
        if self._sort_column is not None:
            visible_results.sort(
                key=lambda result: self._sort_key(result, self._sort_column or ""),
                reverse=self._sort_desc,
            )

        for index, result in enumerate(visible_results):
            tags = ["even" if index % 2 == 0 else "odd"]
            if result.has_errors:
                tags.append("error")
            elif result.has_warnings:
                tags.append("warning")

            self.preview.insert(
                "",
                "end",
                values=(
                    self._value_for_column(result, "artikel_nr"),
                    self._value_for_column(result, "name"),
                    self._value_for_column(result, "brand"),
                    self._value_for_column(result, "plain_description"),
                    self._value_for_column(result, "price"),
                    self._value_for_column(result, "cost"),
                    self._value_for_column(result, "referenznummer"),
                ),
                tags=tuple(tags),
            )

        self._refresh_heading_labels()
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
        """Download issue report for selected severity."""
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

        self._download_issue_csv(severity=severity)


def run_gui() -> None:
    """Start the desktop application event loop."""
    app = ConverterApp()
    app.mainloop()

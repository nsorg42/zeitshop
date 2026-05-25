from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
import importlib
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from types import ModuleType


def _load_sv_ttk() -> ModuleType | None:
    """Load the optional sv_ttk theme module lazily."""
    try:
        module = importlib.import_module("sv_ttk")
    except ModuleNotFoundError:  # pragma: no cover - optional dependency at runtime
        return None
    return module


sv_ttk = _load_sv_ttk()

from ..conversion import convert_diamond_file
from ..core.barcodes import ensure_unique_product_barcodes
from ..core import (
    ConversionBatch,
    ConversionOptions,
    InventoryUpdateBatch,
    Severity,
    ValidationIssue,
)
from ..inventory_update import build_inventory_update_batch
from ..io import (
    ReportDescriptionRecord,
    read_report_description_csv,
    write_issue_csv,
    write_wix_csv,
)
from ..core.validation import validate_wix_row

_SETTINGS_PATH = Path.home() / ".zeitshop_converter" / "gui_settings.json"
_PREVIEW_TO_WIX_COLUMN = {
    "name": "name",
    "brand": "brand",
    "plain_description": "plainDescription",
    "price": "price",
    "cost": "cost",
    "referenznummer": "barcode",
}
_WIX_TO_PREVIEW_COLUMN = {
    wix_column: preview_column
    for preview_column, wix_column in _PREVIEW_TO_WIX_COLUMN.items()
}
_WIX_TO_PREVIEW_COLUMN["sku"] = "artikel_nr"
_EDIT_ERROR_MESSAGES_DE = {
    "name is required.": "Name fehlt.",
    "name exceeds 80 characters.": "Name ist länger als 80 Zeichen.",
    "price is required.": "Preis fehlt.",
    "price must be numeric.": "Preis muss numerisch sein.",
    "cost must be numeric with <=9 whole digits and <=2 decimals.": (
        "Einstand muss numerisch sein (max. 9 Vorkomma- und 2 Nachkommastellen)."
    ),
}


@dataclass
class GuiSettings:
    """Persisted GUI options hidden from the main screen."""

    default_visible: bool = True


def _load_settings() -> GuiSettings:
    """Read GUI settings from disk, falling back to defaults on any issue."""
    if not _SETTINGS_PATH.exists():
        return GuiSettings()

    try:
        payload = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return GuiSettings()

    settings = GuiSettings()
    settings.default_visible = bool(
        payload.get("default_visible", settings.default_visible)
    )
    return settings


def _save_settings(settings: GuiSettings) -> None:
    """Persist GUI settings for the next launch."""
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
        self.update_batch: InventoryUpdateBatch | None = None
        self.diamond_path: Path | None = None
        self.wix_export_path: Path | None = None
        self._conversion_running = False
        self._conversion_events: queue.Queue[tuple[str, object, object | None]] = (
            queue.Queue()
        )

        self.mode_var = tk.StringVar(value="update")
        self.intro_var = tk.StringVar()
        self.card_title_var = tk.StringVar()
        self.primary_action_var = tk.StringVar()
        self.summary_valid_label_var = tk.StringVar()
        self.selected_path_var = tk.StringVar(value="Keine Datei ausgewählt")
        self.selected_wix_path_var = tk.StringVar(value="Keine Wix-Datei ausgewählt")
        self.summary_total_var = tk.StringVar(value="0")
        self.summary_valid_var = tk.StringVar(value="0")
        self.status_var = tk.StringVar(value="Bereit.")
        self.progress_text_var = tk.StringVar(value="")
        self.search_var = tk.StringVar(value="")
        self._primary_button_style = "Primary.TButton"
        self._import_preview_columns = (
            "artikel_nr",
            "name",
            "brand",
            "plain_description",
            "price",
            "inventory",
            "referenznummer",
        )
        self._update_preview_columns = (
            "artikel_nr",
            "name",
            "inventory_old",
            "inventory_new",
            "status",
        )
        self._preview_columns = self._update_preview_columns
        self._column_labels = {
            "artikel_nr": "Artikel Nr",
            "name": "Name",
            "brand": "Marke",
            "plain_description": "Beschreibung",
            "price": "Preis",
            "inventory": "Bestand",
            "referenznummer": "Referenznummer",
            "inventory_old": "Bestand alt",
            "inventory_new": "Bestand neu",
            "status": "Status",
        }
        self._sort_column: str | None = None
        self._sort_desc = False
        self._preview_overrides: dict[int, dict[str, str]] = {}
        self._cell_editor: tk.Widget | None = None
        self._cell_editor_window: tk.Toplevel | None = None
        self._editing_item: str | None = None
        self._editing_column: str | None = None

        self._settings_window: tk.Toplevel | None = None

        self._configure_style()
        self._build_ui()
        self.search_var.trace_add("write", lambda *_args: self._render_preview())
        self.mode_var.trace_add("write", lambda *_args: self._switch_mode())
        self._switch_mode()
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
        style.configure(
            "Header.TLabel",
            background=root_bg,
            font=("Segoe UI", 22, "bold"),
            foreground="#0f172a",
        )
        style.configure(
            "SubHeader.TLabel",
            background=root_bg,
            font=("Segoe UI", 10),
            foreground="#475569",
        )
        style.configure(
            "CardTitle.TLabel",
            background=card_bg,
            font=("Segoe UI", 11, "bold"),
            foreground="#0f172a",
        )
        style.configure("PathValue.TLabel", background=card_bg, foreground="#0f172a")
        style.configure("Muted.TLabel", background=card_bg, foreground="#64748b")
        style.configure(
            "SummaryLabel.TLabel",
            background=card_bg,
            foreground="#334155",
            font=("Segoe UI", 10, "bold"),
        )
        style.configure("SummaryValue.TLabel", background=card_bg, foreground="#0f172a")
        style.configure(
            "Link.TLabel",
            background=card_bg,
            foreground="#2563eb",
            font=("Segoe UI", 10, "underline"),
        )
        style.configure("Secondary.TButton", padding=(12, 8))
        style.configure(
            "Primary.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 10)
        )
        style.configure(
            "Treeview",
            background=card_bg,
            fieldbackground=card_bg,
            foreground="#0f172a",
            rowheight=28,
            borderwidth=0,
        )
        style.map(
            "Treeview",
            background=[("selected", "#dbeafe")],
            foreground=[("selected", "#0f172a")],
        )
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

        ttk.Label(header, text="Zeitshop Konverter", style="Header.TLabel").pack(
            side="left"
        )
        mode_frame = ttk.Frame(header, style="Root.TFrame")
        mode_frame.pack(side="right", padx=(0, 12))
        ttk.Radiobutton(
            mode_frame, text="Update", value="update", variable=self.mode_var
        ).pack(side="left")
        ttk.Radiobutton(
            mode_frame, text="Import", value="import", variable=self.mode_var
        ).pack(side="left", padx=(8, 0))
        ttk.Button(
            header,
            text="Einstellungen",
            style="Secondary.TButton",
            command=self._open_settings_window,
        ).pack(
            side="right",
        )

        ttk.Label(
            root,
            textvariable=self.intro_var,
            style="SubHeader.TLabel",
        ).pack(fill="x", pady=(2, 12))
        ttk.Label(root, textvariable=self.status_var, style="SubHeader.TLabel").pack(
            fill="x", pady=(0, 10)
        )
        self.progressbar = ttk.Progressbar(
            root, orient="horizontal", mode="determinate", maximum=1, value=0
        )
        self.progressbar.pack(fill="x", pady=(0, 2))
        ttk.Label(
            root, textvariable=self.progress_text_var, style="SubHeader.TLabel"
        ).pack(fill="x", pady=(0, 10))

        upload_card = ttk.Frame(root, padding=16, style="Card.TFrame")
        upload_card.pack(fill="x")

        ttk.Label(
            upload_card, textvariable=self.card_title_var, style="CardTitle.TLabel"
        ).grid(
            row=0,
            column=0,
            sticky="w",
        )
        self.primary_action_button = ttk.Button(
            upload_card,
            textvariable=self.primary_action_var,
            style=self._primary_button_style,
            command=self._run_primary_action,
        )
        self.primary_action_button.grid(row=0, column=1, sticky="e")

        self.wix_export_label = ttk.Label(
            upload_card, text="Wix Produkt-Export:", style="Muted.TLabel"
        )
        self.wix_export_label.grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.wix_export_button = ttk.Button(
            upload_card,
            text="Wix-Export auswählen",
            style="Secondary.TButton",
            command=self._select_wix_export,
        )
        self.wix_export_button.grid(row=1, column=1, sticky="e", pady=(12, 0))
        self.wix_export_path_label = ttk.Label(
            upload_card,
            textvariable=self.selected_wix_path_var,
            style="PathValue.TLabel",
            wraplength=820,
        )
        self.wix_export_path_label.grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(2, 0)
        )

        ttk.Label(upload_card, text="Ausgewählte Datei:", style="Muted.TLabel").grid(
            row=3,
            column=0,
            sticky="w",
            pady=(12, 0),
        )
        ttk.Label(
            upload_card,
            textvariable=self.selected_path_var,
            style="PathValue.TLabel",
            wraplength=820,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 0))

        upload_card.columnconfigure(0, weight=1)

        summary_card = ttk.Frame(root, padding=12, style="Card.TFrame")
        summary_card.pack(fill="x", pady=(10, 10))
        summary_grid = ttk.Frame(summary_card, style="Card.TFrame")
        summary_grid.pack(fill="x")

        ttk.Label(summary_grid, text="Zeilen:", style="SummaryLabel.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(
            summary_grid,
            textvariable=self.summary_total_var,
            style="SummaryValue.TLabel",
        ).grid(
            row=0,
            column=1,
            sticky="w",
            padx=(4, 18),
        )

        ttk.Label(
            summary_grid,
            textvariable=self.summary_valid_label_var,
            style="SummaryLabel.TLabel",
        ).grid(
            row=0,
            column=2,
            sticky="w",
        )
        ttk.Label(
            summary_grid,
            textvariable=self.summary_valid_var,
            style="SummaryValue.TLabel",
        ).grid(
            row=0,
            column=3,
            sticky="w",
            padx=(4, 18),
        )

        self.error_link = ttk.Label(
            summary_grid, text="", style="Link.TLabel", cursor="hand2"
        )
        self.error_link.grid(row=0, column=4, sticky="w", padx=(0, 18))
        self.error_link.bind(
            "<Button-1>", lambda _event: self._open_issue_report(Severity.ERROR)
        )

        self.warning_link = ttk.Label(
            summary_grid, text="", style="Link.TLabel", cursor="hand2"
        )
        self.warning_link.grid(row=0, column=5, sticky="w")
        self.warning_link.bind(
            "<Button-1>", lambda _event: self._open_issue_report(Severity.WARNING)
        )

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

        self.add_description_button = ttk.Button(
            actions_row,
            text="Beschreibung hinzufügen",
            style="Secondary.TButton",
            command=self._add_description_from_report_csv,
            state="disabled",
        )
        self.add_description_button.pack(side="left", padx=(8, 0))

        search_row = ttk.Frame(table_card, style="Card.TFrame")
        search_row.pack(fill="x", pady=(0, 8))
        ttk.Label(search_row, text="Suche:", style="Muted.TLabel").pack(side="left")
        ttk.Entry(search_row, textvariable=self.search_var, width=42).pack(
            side="left", padx=(8, 8)
        )
        ttk.Button(
            search_row, text="Löschen", command=lambda: self.search_var.set("")
        ).pack(side="left")

        table_grid = ttk.Frame(table_card, style="Card.TFrame")
        table_grid.pack(fill="both", expand=True)
        table_grid.columnconfigure(0, weight=1)
        table_grid.rowconfigure(0, weight=1)

        self.preview = ttk.Treeview(
            table_grid, columns=self._preview_columns, show="headings", height=18
        )
        self.preview.grid(row=0, column=0, sticky="nsew")

        preview_scrollbar = ttk.Scrollbar(
            table_grid, orient="vertical", command=self.preview.yview
        )
        preview_scrollbar.grid(row=0, column=1, sticky="ns", padx=(8, 0))
        preview_x_scrollbar = ttk.Scrollbar(
            table_grid, orient="horizontal", command=self.preview.xview
        )
        preview_x_scrollbar.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.preview.configure(
            yscrollcommand=preview_scrollbar.set,
            xscrollcommand=preview_x_scrollbar.set,
        )

        for column in self._preview_columns:
            self.preview.heading(
                column,
                text=self._column_labels[column],
                command=lambda selected=column: self._toggle_sort(selected),
            )

        self._configure_preview_columns()

        self.preview.tag_configure("even", background="#ffffff")
        self.preview.tag_configure("odd", background="#f8fafc")
        self.preview.tag_configure("error", background="#ffe4e6")
        self.preview.tag_configure("warning", background="#fff7db")
        self.preview.bind("<Double-1>", self._begin_cell_edit)

    def _is_import_mode(self) -> bool:
        mode_var = getattr(self, "mode_var", None)
        if mode_var is None:
            return True
        return mode_var.get() == "import"

    def _active_results(self) -> list[object]:
        if ConverterApp._is_import_mode(self):
            return [] if self.batch is None else list(self.batch.results)
        return [] if self.update_batch is None else list(self.update_batch.results)

    def _configure_preview_columns(self) -> None:
        """Apply mode-specific table columns and widths."""
        self.preview.configure(columns=self._preview_columns)
        for column in self._preview_columns:
            self.preview.heading(
                column,
                text=self._column_labels[column],
                command=lambda selected=column: self._toggle_sort(selected),
            )

        widths = {
            "artikel_nr": {"width": 110, "anchor": "center"},
            "name": {"width": 280},
            "brand": {"width": 140},
            "plain_description": {"width": 380},
            "price": {"width": 100, "anchor": "e"},
            "inventory": {"width": 100, "anchor": "center"},
            "referenznummer": {"width": 170, "anchor": "center"},
            "inventory_old": {"width": 110, "anchor": "center"},
            "inventory_new": {"width": 110, "anchor": "center"},
            "status": {"width": 120, "anchor": "center"},
        }
        for column in self._preview_columns:
            config = {"stretch": False, **widths.get(column, {"width": 140})}
            self.preview.column(column, **config)

    def _switch_mode(self) -> None:
        """Update mode-specific labels, controls, and transient state."""
        self._close_cell_editor(save=False)
        self.batch = None
        self.update_batch = None
        self.diamond_path = None
        self.wix_export_path = None
        self.selected_path_var.set("Keine Datei ausgewählt")
        self.selected_wix_path_var.set("Keine Wix-Datei ausgewählt")
        self._preview_overrides.clear()
        self._sort_column = None
        self._sort_desc = False
        self.progressbar.configure(value=0)
        self.progress_text_var.set("")

        if ConverterApp._is_import_mode(self):
            self.intro_var.set(
                "DIAMOND-CSV auswählen, konvertieren, und Wix-CSV herunterladen."
            )
            self.card_title_var.set("Diamond Exportdatei")
            self.primary_action_var.set("Datei auswählen und konvertieren")
            self.summary_valid_label_var.set("Gültig:")
            self._preview_columns = self._import_preview_columns
            self.wix_export_label.grid_remove()
            self.wix_export_button.grid_remove()
            self.wix_export_path_label.grid_remove()
            self.add_description_button.configure(state="disabled")
        else:
            self.intro_var.set(
                "Wix-Export und Lager-CSV auswählen, Bestand aktualisieren, und aktualisierte Wix-CSV speichern."
            )
            self.card_title_var.set("Bestandsupdate")
            self.primary_action_var.set("Lagerdatei auswählen und aktualisieren")
            self.summary_valid_label_var.set("Aktualisiert:")
            self._preview_columns = self._update_preview_columns
            self.wix_export_label.grid()
            self.wix_export_button.grid()
            self.wix_export_path_label.grid()
            self.add_description_button.configure(state="disabled")

        self.status_var.set("Bereit.")
        self.download_wix_button.configure(state="disabled")
        self.download_issue_button.configure(state="disabled")
        self._configure_preview_columns()
        self._render_preview()

    def _open_settings_window(self) -> None:
        """Open a focused settings dialog for advanced options."""
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.focus_set()
            return

        window = tk.Toplevel(self)
        window.title("Einstellungen")
        window.geometry("780x640")
        window.minsize(680, 480)
        window.resizable(True, True)
        window.transient(self)
        window.grab_set()
        window.configure(bg="#eef2f6")

        outer = ttk.Frame(window, style="Root.TFrame")
        outer.pack(fill="both", expand=True)

        scroll_area = ttk.Frame(outer, style="Root.TFrame")
        scroll_area.pack(fill="both", expand=True)

        canvas = tk.Canvas(
            scroll_area,
            background="#eef2f6",
            borderwidth=0,
            highlightthickness=0,
        )
        canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(scroll_area, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)

        container = ttk.Frame(canvas, padding=16, style="Root.TFrame")
        container_window = canvas.create_window((0, 0), window=container, anchor="nw")

        def sync_scroll_region(_event: tk.Event | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        def sync_container_width(event: tk.Event) -> None:
            canvas.itemconfigure(container_window, width=event.width)

        def on_mousewheel(event: tk.Event) -> str | None:
            if getattr(event, "delta", 0):
                canvas.yview_scroll(int(-event.delta / 120), "units")
                return "break"
            return None

        container.bind("<Configure>", sync_scroll_region)
        canvas.bind("<Configure>", sync_container_width)
        window.bind("<MouseWheel>", on_mousewheel)
        window.bind("<Button-4>", lambda _event: canvas.yview_scroll(-1, "units"))
        window.bind("<Button-5>", lambda _event: canvas.yview_scroll(1, "units"))

        def close_settings_window() -> None:
            self._settings_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_settings_window)

        ttk.Label(
            container, text="Erweiterte Einstellungen", font=("Segoe UI", 13, "bold")
        ).pack(anchor="w")
        ttk.Label(
            container,
            text=("Diese Optionen beeinflussen die Konvertierung."),
        ).pack(anchor="w", pady=(4, 12))

        visible_var = tk.BooleanVar(value=self.settings.default_visible)

        form = ttk.Frame(container)
        form.pack(fill="x")

        ttk.Checkbutton(
            form,
            text="Alle Produkte im Onlineshop ausstellen",
            variable=visible_var,
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        form.columnconfigure(0, weight=1)

        def on_save() -> None:
            self.settings.default_visible = visible_var.get()

            try:
                _save_settings(self.settings)
            except OSError as exc:
                messagebox.showerror(
                    "Fehler", f"Einstellungen konnten nicht gespeichert werden:\n{exc}"
                )
                return

            self.status_var.set("Einstellungen gespeichert.")
            close_settings_window()

        actions = ttk.Frame(outer, padding=(16, 12, 16, 16), style="Root.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Speichern", command=on_save).pack(side="right")
        ttk.Button(actions, text="Abbrechen", command=close_settings_window).pack(
            side="right", padx=(0, 8)
        )

        sync_scroll_region()
        self._settings_window = window

    def _run_primary_action(self) -> None:
        """Dispatch the primary button to the active mode."""
        if ConverterApp._is_import_mode(self):
            self._select_and_convert()
            return
        self._select_and_update()

    def _select_wix_export(self) -> None:
        """Pick a Wix export CSV used as the base for inventory updates."""
        selected = filedialog.askopenfilename(
            title="Wix Produkt-Export auswählen",
            filetypes=(
                ("Wix CSV Dateien", "*.csv *.CSV"),
                ("CSV Dateien", "*.csv *.CSV"),
                ("Alle Dateien", "*.*"),
            ),
        )
        if not selected:
            return

        self.wix_export_path = Path(selected)
        self.selected_wix_path_var.set(str(self.wix_export_path))
        self.status_var.set("Wix-Export ausgewählt.")

    def _select_and_convert(self) -> None:
        """Pick input file and directly run conversion + export."""
        if self._conversion_running:
            messagebox.showinfo("Hinweis", "Eine Konvertierung läuft bereits.")
            return

        selected = filedialog.askopenfilename(
            title="diamond csv datei auswählen",
            filetypes=(
                ("DIAMOND CSV Dateien", "*.csv *.CSV"),
                ("CSV Dateien", "*.csv *.CSV"),
                ("Alle Dateien", "*.*"),
            ),
        )
        if not selected:
            return

        self.diamond_path = Path(selected)
        self.selected_path_var.set(str(self.diamond_path))
        self._run_conversion()

    def _select_and_update(self) -> None:
        """Pick lager.csv input and update inventory inside an existing Wix export."""
        if self._conversion_running:
            messagebox.showinfo("Hinweis", "Eine Konvertierung läuft bereits.")
            return
        if self.wix_export_path is None:
            messagebox.showerror(
                "Fehlende Datei", "Bitte zuerst den Wix Produkt-Export auswählen."
            )
            return

        selected = filedialog.askopenfilename(
            title="lager csv datei auswählen",
            filetypes=(
                ("DIAMOND CSV Dateien", "*.csv *.CSV"),
                ("CSV Dateien", "*.csv *.CSV"),
                ("Alle Dateien", "*.*"),
            ),
        )
        if not selected:
            return

        self.diamond_path = Path(selected)
        self.selected_path_var.set(str(self.diamond_path))
        self._run_inventory_update()

    def _build_options(self) -> ConversionOptions:
        """Create converter options from persisted settings."""
        return ConversionOptions(
            default_visible=self.settings.default_visible,
            numeric_inventory=True,
            handle_prefix="ds-",
        )

    def _report_progress(self, message: str) -> None:
        """Refresh the status line while long-running work is in progress."""
        self.status_var.set(message)
        if not self.progress_text_var.get():
            self.progress_text_var.set("Fortschritt: läuft")
        self.update_idletasks()

    def _report_progress_async(self, message: str) -> None:
        """Queue worker-thread progress updates for the Tk main loop."""
        self._conversion_events.put(("progress", message, None))

    def _finish_conversion_error(self, exc: Exception) -> None:
        """Reset UI state after a failed background conversion."""
        self._conversion_running = False
        self.configure(cursor="")
        message = str(exc).strip() or "Fehler bei der Konvertierung."
        self.status_var.set(message)
        self.progressbar.configure(value=0)
        self.progress_text_var.set("")
        messagebox.showerror("Konvertierung fehlgeschlagen", message)

    def _finish_conversion_success(
        self, batch: ConversionBatch, options: ConversionOptions
    ) -> None:
        """Apply successful conversion results on the Tk main loop."""
        self._conversion_running = False
        self.configure(cursor="")
        self._close_cell_editor(save=False)
        self._preview_overrides.clear()
        self.update_batch = None
        self.batch = batch
        progress_max = int(float(self.progressbar.cget("maximum")) or 1)
        self.progressbar.configure(value=progress_max)
        if self.progress_text_var.get():
            self.progress_text_var.set(f"{self.progress_text_var.get()} abgeschlossen")

        self._render_preview()
        self.download_wix_button.configure(state="normal")
        has_issues = bool(self.batch.issue_rows)
        self.download_issue_button.configure(
            state="normal" if has_issues else "disabled"
        )
        self.add_description_button.configure(state="normal")

        if has_issues:
            messagebox.showinfo(
                "Konvertierung abgeschlossen",
                (
                    "Die Konvertierung ist abgeschlossen, es gibt aber Fehler oder Warnungen.\n\n"
                    f"Produkte gesamt: {len(self.batch.results)}\n"
                    f"Gültig: {len(self.batch.valid_product_rows)}\n"
                    f"Fehler: {self.batch.error_count}\n"
                    f"Warnungen: {self.batch.warning_count}"
                ),
            )
            self.status_var.set(
                "Konvertierung abgeschlossen mit Fehlern oder Warnungen."
            )
            return

        self.status_var.set("Konvertierung abgeschlossen.")

    def _finish_inventory_update_success(self, batch: InventoryUpdateBatch) -> None:
        """Apply successful inventory-update results on the Tk main loop."""
        self._conversion_running = False
        self.configure(cursor="")
        self._close_cell_editor(save=False)
        self._preview_overrides.clear()
        self.batch = None
        self.update_batch = batch
        progress_max = int(float(self.progressbar.cget("maximum")) or 1)
        self.progressbar.configure(value=progress_max)
        if self.progress_text_var.get():
            self.progress_text_var.set(f"{self.progress_text_var.get()} abgeschlossen")

        self._render_preview()
        self.download_wix_button.configure(state="normal")
        self.download_issue_button.configure(state="disabled")
        self.add_description_button.configure(state="disabled")
        self.status_var.set(
            f"Bestandsupdate abgeschlossen. Aktualisiert: {batch.changed_count}, gefunden: {batch.matched_count}."
        )

    def _poll_conversion_events(self) -> None:
        """Process background conversion events on the Tk main loop."""
        while True:
            try:
                event_type, payload, extra = self._conversion_events.get_nowait()
            except queue.Empty:
                break

            if event_type == "progress":
                self._report_progress(str(payload))
                continue
            if event_type == "error":
                assert isinstance(payload, Exception)
                self._finish_conversion_error(payload)
                continue
            if event_type == "success":
                assert isinstance(payload, ConversionBatch)
                assert isinstance(extra, ConversionOptions)
                self._finish_conversion_success(payload, extra)
                continue
            if event_type == "success_update":
                assert isinstance(payload, InventoryUpdateBatch)
                self._finish_inventory_update_success(payload)
                continue

        if self._conversion_running:
            self.after(100, self._poll_conversion_events)

    def _run_conversion(self) -> None:
        """Convert selected input and keep results in memory until download."""
        if self.diamond_path is None:
            messagebox.showerror(
                "Fehlende Datei", "Bitte zuerst eine DIAMOND-Datei auswählen."
            )
            return
        if self._conversion_running:
            return

        options = self._build_options()

        self._conversion_running = True
        self.status_var.set("Konvertierung läuft...")
        self.progressbar.configure(maximum=1, value=0)
        self.progress_text_var.set("")
        self.configure(cursor="watch")
        self.update_idletasks()

        def worker() -> None:
            try:
                batch = convert_diamond_file(
                    diamond_csv=self.diamond_path,
                    options=options,
                )
            except Exception as exc:  # pragma: no cover - GUI runtime path
                self._conversion_events.put(("error", exc, None))
                return

            self._conversion_events.put(("success", batch, options))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_conversion_events)

    def _run_inventory_update(self) -> None:
        """Update inventory inside a Wix export using the selected lager.csv file."""
        if self.diamond_path is None:
            messagebox.showerror(
                "Fehlende Datei", "Bitte zuerst eine Lager-Datei auswählen."
            )
            return
        if self.wix_export_path is None:
            messagebox.showerror(
                "Fehlende Datei", "Bitte zuerst einen Wix Produkt-Export auswählen."
            )
            return
        if self._conversion_running:
            return

        self._conversion_running = True
        self.status_var.set("Bestandsupdate läuft...")
        self.progressbar.configure(maximum=1, value=0)
        self.progress_text_var.set("")
        self.configure(cursor="watch")
        self.update_idletasks()

        def worker() -> None:
            try:
                batch = build_inventory_update_batch(
                    wix_export_csv=self.wix_export_path,
                    diamond_csv=self.diamond_path,
                )
            except Exception as exc:  # pragma: no cover - GUI runtime path
                self._conversion_events.put(("error", exc, None))
                return

            self._conversion_events.put(("success_update", batch, None))

        threading.Thread(target=worker, daemon=True).start()
        self.after(100, self._poll_conversion_events)

    def _default_download_directory(self) -> Path:
        """Prefer configured output directory, then input-file folder, then home."""
        if not ConverterApp._is_import_mode(self) and self.wix_export_path is not None:
            return self.wix_export_path.parent
        if self.diamond_path is not None:
            return self.diamond_path.parent
        return Path.home()

    def _default_wix_filename(self) -> str:
        """Build default Wix export filename based on source file name."""
        if ConverterApp._is_import_mode(self):
            if self.diamond_path is None:
                return "wix_import.csv"
            return f"{self.diamond_path.stem}_wix_import.csv"
        if self.wix_export_path is None:
            return "wix_inventory_update.csv"
        return f"{self.wix_export_path.stem}_inventory_update.csv"

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
        if ConverterApp._is_import_mode(self) and self.batch is None:
            messagebox.showerror("Keine Daten", "Bitte zuerst eine Datei konvertieren.")
            return
        if not ConverterApp._is_import_mode(self) and self.update_batch is None:
            messagebox.showerror(
                "Keine Daten", "Bitte zuerst ein Bestandsupdate ausführen."
            )
            return
        self._close_cell_editor(save=True)

        export_rows, export_errors = self._build_export_rows()
        if export_errors:
            preview = "\n".join(
                self._format_export_error(issue) for issue in export_errors[:5]
            )
            remaining = len(export_errors) - min(len(export_errors), 5)
            if remaining > 0:
                preview = f"{preview}\n... und {remaining} weitere."
            messagebox.showerror(
                "Ungültige Bearbeitung",
                (
                    "Mindestens eine bearbeitete Tabellenzelle enthält ungültige Daten. "
                    "Bitte korrigiere die markierten Werte vor dem Export.\n\n"
                    f"{preview}"
                ),
            )
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
            active_header = (
                self.batch.header
                if ConverterApp._is_import_mode(self)
                else self.update_batch.header
            )
            write_wix_csv(path=target, header=active_header, rows=export_rows)
        except OSError as exc:
            messagebox.showerror(
                "Dateifehler", f"Wix-CSV konnte nicht gespeichert werden:\n{exc}"
            )
            return

        messagebox.showinfo("Export", f"Wix-CSV gespeichert: {Path(target).name}")

    def _download_issue_csv(self, severity: Severity | None = None) -> None:
        """Save issue rows (all, only errors, or only warnings) to CSV."""
        if self.batch is None:
            messagebox.showerror("Keine Daten", "Bitte zuerst eine Datei konvertieren.")
            return
        self._close_cell_editor(save=True)

        if severity is None:
            issue_rows = self.batch.issue_rows
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
            messagebox.showerror(
                "Dateifehler", f"Bericht konnte nicht gespeichert werden:\n{exc}"
            )
            return

        messagebox.showinfo("Export", f"Bericht gespeichert: {Path(target).name}")

    def _add_description_from_report_csv(self) -> None:
        """Load a report.csv export and merge descriptions into the description column."""
        if not ConverterApp._is_import_mode(self) or self.batch is None:
            messagebox.showerror(
                "Keine Daten", "Bitte zuerst eine Lager-Datei konvertieren."
            )
            return
        self._close_cell_editor(save=True)

        selected = filedialog.askopenfilename(
            title="report.csv auswählen",
            filetypes=(
                ("CSV Dateien", "*.csv *.CSV"),
                ("Alle Dateien", "*.*"),
            ),
        )
        if not selected:
            return

        try:
            descriptions = read_report_description_csv(selected)
        except (OSError, ValueError) as exc:
            messagebox.showerror(
                "Dateifehler", f"Beschreibung konnte nicht gelesen werden:\n{exc}"
            )
            return

        matched_rows = self._apply_report_descriptions(descriptions)
        if matched_rows == 0:
            messagebox.showerror(
                "Keine Zuordnung",
                "Es konnten keine passenden Produkte aus der Report-Datei zugeordnet werden.",
            )
            return

        self._render_preview()
        self.status_var.set(
            f"Beschreibung ergänzt: {matched_rows} Produkte aktualisiert."
        )

    def _apply_report_descriptions(
        self, descriptions: list[ReportDescriptionRecord]
    ) -> int:
        """Match report descriptions against current rows and store them as preview overrides."""
        if self.batch is None:
            return 0

        by_artikel_nr = {
            description.artikel_nr: description.beschreibung
            for description in descriptions
            if description.artikel_nr
        }
        by_referenz = {
            description.referenz: description.beschreibung
            for description in descriptions
            if description.referenz
        }

        matched_rows = 0
        for result in self.batch.results:
            artikel_nr = result.source.get("Artikel Nr", "").strip()
            referenz = result.source.get("Referenz", "").strip()

            beschreibung = ""
            if artikel_nr:
                beschreibung = by_artikel_nr.get(artikel_nr, "")
            if not beschreibung and referenz:
                beschreibung = by_referenz.get(referenz, "")
            if not beschreibung:
                continue

            existing = self._value_for_column(result, "plain_description").strip()
            merged_description = beschreibung
            if existing and existing != beschreibung:
                merged_description = f"{beschreibung}\n{existing}"

            self._store_preview_override(
                result, "plain_description", merged_description
            )
            matched_rows += 1

        return matched_rows

    def _base_value_for_column(self, result, column: str) -> str:
        """Return the original value for one preview column."""
        if not ConverterApp._is_import_mode(self):
            if column == "artikel_nr":
                return result.wix_row.get("sku", "")
            if column == "name":
                return result.wix_row.get("name", "")
            if column == "inventory_old":
                return result.original_inventory
            if column == "inventory_new":
                return result.updated_inventory
            if column == "status":
                if result.changed:
                    return "Aktualisiert"
                if result.matched:
                    return "Gefunden"
                return "Nicht gefunden"
            return ""
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
        if column == "inventory":
            return result.wix_row.get("inventory", "")
        if column == "referenznummer":
            return result.wix_row.get("barcode", "")
        return ""

    def _value_for_column(self, result, column: str) -> str:
        """Return displayed value for a preview column, including manual edits."""
        if not ConverterApp._is_import_mode(self):
            return self._base_value_for_column(result, column)
        overrides = self._preview_overrides.get(result.source_row, {})
        if column in overrides:
            return overrides[column]
        return self._base_value_for_column(result, column)

    def _preview_item_id(self, result) -> str:
        """Build a stable Treeview row id from the source row number."""
        return f"row-{result.source_row}"

    def _preview_column_from_tree_id(self, tree_column: str) -> str | None:
        """Translate Treeview '#1' style ids into preview column names."""
        if not tree_column.startswith("#"):
            return None
        try:
            column_index = int(tree_column[1:]) - 1
        except ValueError:
            return None
        if 0 <= column_index < len(self._preview_columns):
            return self._preview_columns[column_index]
        return None

    def _result_for_item(self, item_id: str):
        """Resolve a Treeview item id back to the matching conversion result."""
        results = self._active_results()
        if not results or not item_id.startswith("row-"):
            return None
        try:
            source_row = int(item_id.removeprefix("row-"))
        except ValueError:
            return None
        return next(
            (result for result in results if result.source_row == source_row), None
        )

    def _store_preview_override(self, result, column: str, value: str) -> None:
        """Persist one manually edited preview value."""
        normalized_value = value.strip()
        base_value = self._base_value_for_column(result, column)
        row_overrides = dict(self._preview_overrides.get(result.source_row, {}))

        if normalized_value == base_value:
            row_overrides.pop(column, None)
        else:
            row_overrides[column] = normalized_value

        if row_overrides:
            self._preview_overrides[result.source_row] = row_overrides
        else:
            self._preview_overrides.pop(result.source_row, None)

    def _close_cell_editor(self, *, save: bool) -> None:
        """Close the active inline editor and optionally persist its value."""
        if self._cell_editor is None:
            return

        editor = self._cell_editor
        editor_window = self._cell_editor_window
        item_id = self._editing_item
        column = self._editing_column
        if save:
            if isinstance(editor, tk.Text):
                value = editor.get("1.0", "end-1c")
            else:
                value = editor.get()
        else:
            value = ""

        if editor_window is not None and editor_window.winfo_exists():
            editor_window.destroy()
        else:
            editor.destroy()
        self._cell_editor = None
        self._cell_editor_window = None
        self._editing_item = None
        self._editing_column = None

        if not save or item_id is None or column is None:
            return

        result = self._result_for_item(item_id)
        if result is None:
            return
        self._store_preview_override(result, column, value)

    def _commit_cell_edit(self, _event: tk.Event | None = None) -> str:
        """Persist the current inline edit and refresh the preview."""
        self._close_cell_editor(save=True)
        self._render_preview()
        return "break"

    def _cancel_cell_edit(self, _event: tk.Event | None = None) -> str:
        """Discard the current inline edit."""
        self._close_cell_editor(save=False)
        return "break"

    def _open_description_editor(self, item_id: str, column: str) -> str:
        """Open a larger editor popup for long description fields."""
        root_x = self.winfo_rootx() + 80
        root_y = self.winfo_rooty() + 120
        window = tk.Toplevel(self)
        window.title("Beschreibung bearbeiten")
        window.geometry(f"720x320+{root_x}+{root_y}")
        window.transient(self)
        window.configure(bg="#eef2f6")

        frame = ttk.Frame(window, padding=12, style="Root.TFrame")
        frame.pack(fill="both", expand=True)

        text = tk.Text(
            frame,
            wrap="word",
            font=("Segoe UI", 10),
            relief="solid",
            borderwidth=1,
            undo=True,
        )
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
        text.configure(yscrollcommand=scrollbar.set)
        text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", padx=(8, 0))

        text.insert("1.0", self.preview.set(item_id, column))
        text.focus_set()

        actions = ttk.Frame(window, padding=(12, 0, 12, 12), style="Root.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Speichern", command=self._commit_cell_edit).pack(
            side="right"
        )
        ttk.Button(actions, text="Abbrechen", command=self._cancel_cell_edit).pack(
            side="right", padx=(0, 8)
        )

        text.bind("<Escape>", self._cancel_cell_edit)
        text.bind("<Control-Return>", self._commit_cell_edit)
        window.protocol("WM_DELETE_WINDOW", self._cancel_cell_edit)

        self._cell_editor = text
        self._cell_editor_window = window
        self._editing_item = item_id
        self._editing_column = column
        return "break"

    def _begin_cell_edit(self, event: tk.Event) -> str | None:
        """Open a simple inline editor when the user double-clicks a table cell."""
        if (
            not ConverterApp._is_import_mode(self)
            or self.batch is None
            or self.preview.identify_region(event.x, event.y) != "cell"
        ):
            return None

        item_id = self.preview.identify_row(event.y)
        tree_column = self.preview.identify_column(event.x)
        column = self._preview_column_from_tree_id(tree_column)
        if not item_id or column is None:
            return None

        bbox = self.preview.bbox(item_id, tree_column)
        if not bbox:
            return None

        self._close_cell_editor(save=True)

        if column == "plain_description":
            return self._open_description_editor(item_id, column)

        x_pos, y_pos, width, height = bbox
        editor = ttk.Entry(self.preview)
        editor.place(x=x_pos, y=y_pos, width=width, height=height)
        editor.insert(0, self.preview.set(item_id, column))
        editor.select_range(0, "end")
        editor.focus_set()
        editor.bind("<Return>", self._commit_cell_edit)
        editor.bind("<KP_Enter>", self._commit_cell_edit)
        editor.bind("<Escape>", self._cancel_cell_edit)
        editor.bind("<FocusOut>", self._commit_cell_edit)

        self._cell_editor = editor
        self._cell_editor_window = None
        self._editing_item = item_id
        self._editing_column = column
        return "break"

    def _product_row_for_export(self, result) -> dict[str, str]:
        """Merge edited preview values back into the PRODUCT row for export."""
        row = dict(result.wix_row)
        overrides = self._preview_overrides.get(result.source_row, {})

        for column, value in overrides.items():
            if column == "artikel_nr":
                row["sku"] = value
                continue
            if column == "plain_description":
                row["plainDescription"] = value
                if "Beschreibung" in row:
                    row["Beschreibung"] = value
                continue

            wix_column = _PREVIEW_TO_WIX_COLUMN.get(column)
            if wix_column is not None:
                row[wix_column] = value

        return row

    def _build_export_rows(self) -> tuple[list[dict[str, str]], list[ValidationIssue]]:
        """Build export rows from the current preview state and validate manual edits."""
        if not ConverterApp._is_import_mode(self):
            if self.update_batch is None:
                return [], []
            return [dict(row) for row in self.update_batch.rows], []
        if self.batch is None:
            return [], []

        rows: list[dict[str, str]] = []
        errors: list[ValidationIssue] = []
        products: list[tuple[int, dict[str, str]]] = []
        for result in self.batch.results:
            if result.has_errors:
                continue

            product_row = self._product_row_for_export(result)
            row_errors = [
                issue
                for issue in validate_wix_row(product_row, source_row=result.source_row)
                if issue.severity == Severity.ERROR
            ]
            if row_errors:
                errors.extend(row_errors)
                continue

            products.append((result.source_row, product_row))

        ensure_unique_product_barcodes(products)

        for _source_row, product_row in products:
            rows.append(product_row)

        return rows, errors

    def _format_export_error(self, issue: ValidationIssue) -> str:
        """Format one edited-row validation problem for the GUI."""
        preview_column = _WIX_TO_PREVIEW_COLUMN.get(issue.field, issue.field)
        label = self._column_labels.get(preview_column, issue.field)
        message = _EDIT_ERROR_MESSAGES_DE.get(issue.message, issue.message)
        return f"Zeile {issue.source_row}, {label}: {message}"

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
        if column in {
            "artikel_nr",
            "price",
            "inventory",
            "inventory_old",
            "inventory_new",
        }:
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
        self._close_cell_editor(save=True)
        results = self._active_results()
        if not results:
            for item in self.preview.get_children():
                self.preview.delete(item)
            self._refresh_heading_labels()
            self._update_summary_metrics()
            return

        for item in self.preview.get_children():
            self.preview.delete(item)

        visible_results = [result for result in results if self._matches_search(result)]
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
                iid=self._preview_item_id(result),
                values=tuple(
                    self._value_for_column(result, column)
                    for column in self._preview_columns
                ),
                tags=tuple(tags),
            )

        self._refresh_heading_labels()
        self._update_summary_metrics()

    def _update_summary_metrics(self) -> None:
        """Refresh summary counters and clickable issue links."""
        if ConverterApp._is_import_mode(self):
            if self.batch is None:
                total = 0
                valid = 0
                error_count = 0
                warning_count = 0
            else:
                total = len(self.batch.results)
                valid = len(self.batch.valid_product_rows)
                error_count = self.batch.error_count
                warning_count = self.batch.warning_count
        else:
            total = 0 if self.update_batch is None else len(self.update_batch.results)
            valid = 0 if self.update_batch is None else self.update_batch.changed_count
            error_count = 0
            warning_count = 0

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
        if not ConverterApp._is_import_mode(self):
            messagebox.showinfo(
                "Hinweis", "Im Update-Modus gibt es keinen Fehlerbericht."
            )
            return
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

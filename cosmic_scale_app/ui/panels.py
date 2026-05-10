import datetime
import tkinter as tk
from tkinter import ttk
from typing import Optional

from ..core.shared import (
    ASTRO_YEAR_SECONDS,
    EVENT_COLORS,
    PALETTE,
    date_to_years_ago,
    parse_years_ago,
    session_now,
)
def _pick_unit(years_ago: float) -> tuple[str, float]:
    """Choose the most readable unit + multiplier for an amount in years."""
    y = abs(years_ago)
    if y >= 1e9: return "milliards (Ga)", 1e9
    if y >= 1e6: return "millions (Ma)",  1e6
    if y >= 1e3: return "milliers (ka)",  1e3
    return "années", 1.0


_AGO_UNITS = ["années", "milliers (ka)", "millions (Ma)", "milliards (Ga)"]


def _ago_unit_mult(unit_str: str) -> float:
    if "Ga" in unit_str or "milliard" in unit_str: return 1e9
    if "Ma" in unit_str or "million"  in unit_str: return 1e6
    if "ka" in unit_str or "millier"  in unit_str: return 1e3
    return 1.0


class EditDialog(tk.Toplevel):
    """
    Edit an event or a period. `kind` is "event" or "period".
    `on_save(payload: dict)` is invoked with new values when the user clicks
    Enregistrer. Payload keys depend on kind.
    """

    def __init__(self, parent, kind: str, item, on_save, tags=None):
        super().__init__(parent)
        self.kind    = kind
        self.item    = item
        self.on_save = on_save
        self.tags    = list(tags or ["Non-classés"])

        self.title("Modifier l'évènement" if kind == "event"
                    else "Modifier la période")
        self.configure(bg=PALETTE["bg"])
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)

        self._build()

        # Center over parent
        self.update_idletasks()
        try:
            px = parent.winfo_rootx()
            py = parent.winfo_rooty()
            pw = parent.winfo_width()
            ph = parent.winfo_height()
            w  = self.winfo_width()
            h  = self.winfo_height()
            self.geometry(f"+{px + (pw - w)//2}+{py + (ph - h)//2}")
        except Exception:
            pass

        self.bind("<Escape>", lambda _: self.destroy())

    def _build(self):
        outer = ttk.Frame(self, style="Panel.TFrame")
        outer.pack(fill="both", expand=True, padx=2, pady=2)

        ttk.Label(outer,
                  text=("Modifier l'évènement" if self.kind == "event"
                        else "Modifier la période"),
                  style="Section.TLabel").grid(row=0, column=0, columnspan=2,
                                                sticky="w", padx=12, pady=(12, 6))

        # ── Name ──────────────────────────────────────────────────────────────
        ttk.Label(outer, text="Nom :", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", padx=(12, 6), pady=4)
        self._name_var = tk.StringVar(value=self.item.name)
        ttk.Entry(outer, textvariable=self._name_var, width=44).grid(
            row=1, column=1, sticky="ew", padx=(0, 12), pady=4)
        ttk.Label(outer, text="Groupe :", style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", padx=(12, 6), pady=4)
        current_group = getattr(self.item, "group_name", "Non-classés")
        # Find the matching hierarchical label (« Parent ▸ Enfant ») in `self.tags`.
        match = next((label for label in self.tags
                      if label.rsplit(" ▸ ", 1)[-1].strip() == current_group),
                     current_group)
        self._group_var = tk.StringVar(value=match)
        ttk.Combobox(outer, textvariable=self._group_var,
                      values=self.tags, state="readonly", width=42).grid(
            row=2, column=1, sticky="w", padx=(0, 12), pady=4)

        # ── Mode toggle (Date / Il y a) ───────────────────────────────────────
        # Default to Date mode if the item already has an absolute date.
        has_abs = (
            (self.kind == "event"  and getattr(self.item, "absolute_date", None))
            or (self.kind == "period" and (
                getattr(self.item, "absolute_date_start", None) or
                getattr(self.item, "absolute_date_end", None)))
        )
        self._mode_var = tk.StringVar(value="date" if has_abs else "ago")

        ttk.Label(outer, text="Saisie :", style="Muted.TLabel").grid(
            row=3, column=0, sticky="w", padx=(12, 6), pady=(8, 2))
        mode_row = ttk.Frame(outer, style="Panel.TFrame")
        mode_row.grid(row=3, column=1, sticky="w", padx=(0, 12), pady=(8, 2))
        ttk.Radiobutton(mode_row, text="Date / Heure", variable=self._mode_var,
                         value="date", command=self._on_mode_change).pack(
            side="left", padx=(0, 8))
        ttk.Radiobutton(mode_row, text="Il y a…", variable=self._mode_var,
                         value="ago", command=self._on_mode_change).pack(
            side="left")

        # ── "En cours" toggle (periods only) ──────────────────────────────────
        if self.kind == "period":
            self._ongoing_var = tk.BooleanVar(
                value=bool(getattr(self.item, "is_ongoing", False)))
            tk.Checkbutton(
                outer, text="En cours (la fin est « maintenant »)",
                variable=self._ongoing_var,
                command=self._on_dialog_ongoing_change,
                bg=PALETTE["panel"], fg=PALETTE["text"],
                activebackground=PALETTE["panel"],
                activeforeground=PALETTE["text"],
                selectcolor=PALETTE["entry"], highlightthickness=0,
                font=("Segoe UI", 9)).grid(
                row=4, column=0, columnspan=2, sticky="w", padx=12, pady=(2, 4))
            swap_row = 5
            desc_row = 6
        else:
            self._ongoing_var = None
            swap_row = 4
            desc_row = 5

        # ── Container that swaps date / ago panels ────────────────────────────
        swap = ttk.Frame(outer, style="Panel.TFrame")
        swap.grid(row=swap_row, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        swap.columnconfigure(0, weight=1)

        self._date_panel = ttk.Frame(swap, style="Panel.TFrame")
        self._ago_panel  = ttk.Frame(swap, style="Panel.TFrame")
        self._date_panel.grid(row=0, column=0, sticky="ew")
        self._ago_panel.grid(row=0, column=0, sticky="ew")

        if self.kind == "event":
            self._build_event_ago(self._ago_panel)
            self._build_event_date(self._date_panel)
        else:
            self._build_period_ago(self._ago_panel)
            self._build_period_date(self._date_panel)

        # Show the right panel based on current mode.
        self._on_mode_change()
        # Apply ongoing greyout if it was already checked.
        if self._ongoing_var is not None:
            self._on_dialog_ongoing_change()

        # ── Description ───────────────────────────────────────────────────────
        ttk.Label(outer, text="Description :", style="Muted.TLabel").grid(
            row=desc_row, column=0, sticky="nw", padx=(12, 6), pady=(8, 4))
        self._desc_text = tk.Text(outer, height=5, width=46,
                                    bg=PALETTE["entry"], fg=PALETTE["text"],
                                    insertbackground=PALETTE["text"],
                                    relief="flat", bd=4,
                                    font=("Segoe UI", 9), wrap="word",
                                    highlightthickness=1,
                                    highlightbackground=PALETTE["border"],
                                    highlightcolor=PALETTE["accent"])
        self._desc_text.grid(row=desc_row, column=1, sticky="ew",
                              padx=(0, 12), pady=(8, 4))
        if self.item.description:
            self._desc_text.insert("1.0", self.item.description)

        # ── Buttons ───────────────────────────────────────────────────────────
        btns = ttk.Frame(outer, style="Panel.TFrame")
        btns.grid(row=desc_row + 1, column=0, columnspan=2,
                   sticky="e", padx=12, pady=12)
        ttk.Button(btns, text="Annuler",
                   style="Small.TButton",
                   command=self.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(btns, text="Enregistrer",
                   style="Accent.TButton",
                   command=self._on_save).pack(side="right")

        # Error label
        self._err_var = tk.StringVar()
        ttk.Label(outer, textvariable=self._err_var,
                  foreground=PALETTE["accent2"],
                  background=PALETTE["panel"],
                  font=("Segoe UI", 9), wraplength=420).grid(
            row=desc_row + 2, column=0, columnspan=2,
            sticky="w", padx=12, pady=(0, 8))

    # ── Mode panel builders ───────────────────────────────────────────────────

    def _on_mode_change(self):
        if self._mode_var.get() == "date":
            self._ago_panel.grid_remove()
            self._date_panel.grid()
        else:
            self._date_panel.grid_remove()
            self._ago_panel.grid()
        # Re-apply ongoing greyout if active.
        if getattr(self, "_ongoing_var", None) is not None:
            self._on_dialog_ongoing_change()

    def _on_dialog_ongoing_change(self):
        """Disable the « Fin / End » entries when the period is ongoing."""
        if self._ongoing_var is None: return
        ongoing = self._ongoing_var.get()
        # Date panel: fin entries are stored under attrs starting with "_de_"
        date_end_widgets = [w for w in self._date_panel.winfo_children()
                            if isinstance(w, ttk.Frame)]
        for child in self._date_panel.winfo_children():
            try: info = child.grid_info()
            except Exception: continue
            # The "Fin (date)" header label is at row=1, the entry-wrap at row=1 column=1
            if info.get("row") == 1:
                self._set_subtree_state(child, "disabled" if ongoing else "normal")

        # Ago panel: fin entry at row=1 column=1 (we used the same row layout via _build_ago_row)
        for child in self._ago_panel.winfo_children():
            try: info = child.grid_info()
            except Exception: continue
            if info.get("row") == 1:
                self._set_subtree_state(child, "disabled" if ongoing else "normal")

    @staticmethod
    def _set_subtree_state(widget, state):
        try:
            if isinstance(widget, ttk.Combobox):
                widget.configure(state=("disabled" if state == "disabled" else "readonly"))
            else:
                widget.configure(state=state)
        except tk.TclError:
            pass
        for child in getattr(widget, "winfo_children", lambda: [])():
            EditDialog._set_subtree_state(child, state)

    def _build_event_ago(self, parent):
        self._build_ago_row(parent, row=0, label="Il y a (années) :",
                             var_attr="_years_var",
                             combo_attr="_unit_combo",
                             value=self.item.years_ago)

    def _build_period_ago(self, parent):
        self._build_ago_row(parent, row=0, label="Début (le + ancien) :",
                             var_attr="_ys_var", combo_attr="_us_combo",
                             value=self.item.years_ago_start)
        self._build_ago_row(parent, row=1, label="Fin (le + récent) :",
                             var_attr="_ye_var", combo_attr="_ue_combo",
                             value=self.item.years_ago_end)

    def _build_event_date(self, parent):
        dt = self._parse_iso(getattr(self.item, "absolute_date", None))
        self._build_date_row(parent, row=0, label="Date / Heure :",
                              prefix="ev",
                              dt=dt or session_now())

    def _build_period_date(self, parent):
        dt_s = self._parse_iso(getattr(self.item, "absolute_date_start", None))
        dt_e = self._parse_iso(getattr(self.item, "absolute_date_end",   None))
        self._build_date_row(parent, row=0, label="Début (date) :",
                              prefix="ds",
                              dt=dt_s or session_now())
        self._build_date_row(parent, row=1, label="Fin (date) :",
                              prefix="de",
                              dt=dt_e or session_now())

    def _build_date_row(self, parent, row: int, label: str,
                         prefix: str, dt: datetime.datetime):
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(
            row=row, column=0, sticky="w", padx=(12, 6), pady=4)
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.grid(row=row, column=1, sticky="w", padx=(0, 12), pady=4)

        for i, (val, w) in enumerate([
            (dt.year,  6), (dt.month, 3), (dt.day,    3),
            (dt.hour,  3), (dt.minute, 3), (dt.second, 3),
        ]):
            attr = f"_{prefix}_{['y','m','d','h','mn','s'][i]}_var"
            var = tk.StringVar(value=str(val))
            setattr(self, attr, var)
            ttk.Entry(wrap, textvariable=var, width=w,
                       font=("Segoe UI", 10)).pack(side="left", padx=(0, 4))

        ttk.Label(wrap, text="(an / mois / j / h / min / s)",
                  style="Muted.TLabel",
                  font=("Segoe UI", 8, "italic")).pack(side="left", padx=(6, 0))

    @staticmethod
    def _parse_iso(s: Optional[str]) -> Optional[datetime.datetime]:
        if not s:
            return None
        try:
            return datetime.datetime.fromisoformat(s)
        except (ValueError, TypeError):
            return None

    def _read_date(self, prefix: str) -> Optional[datetime.datetime]:
        try:
            return datetime.datetime(
                int(getattr(self, f"_{prefix}_y_var").get()),
                int(getattr(self, f"_{prefix}_m_var").get()),
                int(getattr(self, f"_{prefix}_d_var").get()),
                int(getattr(self, f"_{prefix}_h_var").get()),
                int(getattr(self, f"_{prefix}_mn_var").get()),
                int(getattr(self, f"_{prefix}_s_var").get()))
        except (ValueError, AttributeError, TypeError):
            return None

    @staticmethod
    def _datetime_to_years_ago(dt: datetime.datetime) -> float:
        return (session_now() - dt).total_seconds() / ASTRO_YEAR_SECONDS

    def _build_ago_row(self, parent, row: int, label: str,
                        var_attr: str, combo_attr: str, value: float):
        ttk.Label(parent, text=label, style="Muted.TLabel").grid(
            row=row, column=0, sticky="w", padx=(12, 6), pady=4)

        unit_str, mult = _pick_unit(value)
        var = tk.StringVar(value=f"{value / mult:g}")
        setattr(self, var_attr, var)

        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.grid(row=row, column=1, sticky="w", padx=(0, 12), pady=4)
        ttk.Entry(wrap, textvariable=var, width=14,
                   font=("Segoe UI", 10)).pack(side="left")
        combo = ttk.Combobox(wrap, values=_AGO_UNITS,
                              state="readonly", width=16)
        combo.set(unit_str)
        combo.pack(side="left", padx=(6, 0))
        setattr(self, combo_attr, combo)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _parse_ago(self, var: tk.StringVar, combo: ttk.Combobox) -> Optional[float]:
        try:
            v = float(var.get().replace(",", ".").replace(" ", ""))
        except ValueError:
            return None
        return v * _ago_unit_mult(combo.get())

    def _on_save(self):
        self._err_var.set("")
        name = self._name_var.get().strip()
        if not name:
            self._err_var.set("Le nom ne peut pas être vide.")
            return
        desc = self._desc_text.get("1.0", "end").strip()
        # Strip a hierarchical prefix « Parent ▸ » to keep just the leaf name.
        raw_group = self._group_var.get().strip() or "Non-classés"
        group_name = raw_group.rsplit(" ▸ ", 1)[-1].strip() or "Non-classés"

        date_mode = (self._mode_var.get() == "date")

        if self.kind == "event":
            absolute_date = None
            if date_mode:
                dt = self._read_date("ev")
                if dt is None:
                    self._err_var.set("Date invalide.")
                    return
                ya = self._datetime_to_years_ago(dt)
                absolute_date = dt.isoformat(timespec="microseconds")
            else:
                ya = self._parse_ago(self._years_var, self._unit_combo)
                if ya is None:
                    self._err_var.set("Valeur 'il y a' invalide.")
                    return
            self.on_save(dict(
                name=name, description=desc, years_ago=ya,
                absolute_date=absolute_date,
                group_name=group_name))
        else:
            ongoing = bool(self._ongoing_var and self._ongoing_var.get())
            abs_start = abs_end = None
            if date_mode:
                dt_s = self._read_date("ds")
                if dt_s is None:
                    self._err_var.set("Date de début invalide.")
                    return
                ys = self._datetime_to_years_ago(dt_s)
                abs_start = dt_s.isoformat(timespec="microseconds")
                if ongoing:
                    ye = 0.0
                    abs_end = None
                else:
                    dt_e = self._read_date("de")
                    if dt_e is None:
                        self._err_var.set("Date de fin invalide.")
                        return
                    ye = self._datetime_to_years_ago(dt_e)
                    abs_end = dt_e.isoformat(timespec="microseconds")
            else:
                ys = self._parse_ago(self._ys_var, self._us_combo)
                if ys is None:
                    self._err_var.set("Valeur début invalide.")
                    return
                if ongoing:
                    ye = 0.0
                else:
                    ye = self._parse_ago(self._ye_var, self._ue_combo)
                    if ye is None:
                        self._err_var.set("Valeur fin invalide.")
                        return
            if not ongoing and ye > ys:
                ys, ye = ye, ys
                abs_start, abs_end = abs_end, abs_start
            if not ongoing and abs(ys - ye) < 1e-9:
                self._err_var.set("Le début et la fin sont identiques.")
                return
            self.on_save(dict(
                name=name, description=desc,
                years_ago_start=ys, years_ago_end=ye,
                absolute_date_start=abs_start,
                absolute_date_end=abs_end,
                is_ongoing=ongoing,
                group_name=group_name))
        self.destroy()


# ── Event Input Panel ──────────────────────────────────────────────────────────

class EventInputPanel(ttk.Frame):
    def __init__(self, parent, on_add, on_add_period,
                 tag_names_provider=None, **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self.on_add        = on_add
        self.on_add_period = on_add_period
        self.tag_names_provider = tag_names_provider or (lambda: ["Non-classés"])
        self._color_idx = 0
        self._tag_vars: dict[str, tk.BooleanVar] = {}
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        ttk.Label(self, text="Ajouter un évènement",
                  style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        # ── Notebook tabs ──────────────────────────────────────────────────────
        nb = ttk.Notebook(self)
        nb.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        self._notebook = nb

        tab_ago    = ttk.Frame(nb, style="Panel.TFrame")
        tab_date   = ttk.Frame(nb, style="Panel.TFrame")
        tab_period = ttk.Frame(nb, style="Panel.TFrame")
        nb.add(tab_ago,    text=" Il y a… ")
        nb.add(tab_date,   text=" Date / Heure ")
        nb.add(tab_period, text=" Période ")

        self._build_ago_tab(tab_ago)
        self._build_date_tab(tab_date)
        self._build_period_tab(tab_period)
        nb.bind("<<NotebookTabChanged>>", self._on_tab_change)

        # ── Name + description ────────────────────────────────────────────────
        name_row = ttk.Frame(self, style="Panel.TFrame")
        name_row.grid(row=2, column=0, sticky="ew", padx=8, pady=(2, 0))
        name_row.columnconfigure(1, weight=1)
        ttk.Label(name_row, text="Nom :", style="Muted.TLabel").grid(
            row=0, column=0, padx=(2, 6), sticky="w")
        self._name_var = tk.StringVar()
        ttk.Entry(name_row, textvariable=self._name_var).grid(
            row=0, column=1, sticky="ew")

        ttk.Label(name_row, text="Description :",
                  style="Muted.TLabel").grid(row=1, column=0,
                                              padx=(2, 6), sticky="nw",
                                              pady=(4, 0))
        self._desc_text = tk.Text(name_row, height=3,
                                    bg=PALETTE["entry"], fg=PALETTE["text"],
                                    insertbackground=PALETTE["text"],
                                    relief="flat", bd=4,
                                    font=("Segoe UI", 9), wrap="word",
                                    highlightthickness=1,
                                    highlightbackground=PALETTE["border"],
                                    highlightcolor=PALETTE["accent"])
        self._desc_text.grid(row=1, column=1, sticky="ew", pady=(4, 0))

        self._tags_frame = ttk.Frame(self, style="Panel.TFrame")
        self._tags_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(6, 0))
        self._tags_frame.columnconfigure(0, weight=1)
        ttk.Label(self._tags_frame, text="Groupe :", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(2, 0), pady=(0, 4))
        self._group_var = tk.StringVar(value="Non-classés")
        self._group_combo = ttk.Combobox(
            self._tags_frame, textvariable=self._group_var,
            state="readonly")
        self._group_combo.grid(row=1, column=0, sticky="ew")
        self.refresh_tag_choices()

        # ── Add button (label updates with the active tab) ────────────────────
        self._add_btn_text = tk.StringVar(value="＋  Ajouter l'évènement")
        self._add_btn = ttk.Button(self, textvariable=self._add_btn_text,
                                    style="Accent.TButton",
                                    command=self._on_add_click)
        self._add_btn.grid(row=4, column=0, sticky="ew", padx=8, pady=8)

        self._err_var = tk.StringVar()
        ttk.Label(self, textvariable=self._err_var,
                  foreground=PALETTE["accent2"],
                  background=PALETTE["panel"],
                  font=("Segoe UI", 8), wraplength=260).grid(
            row=5, column=0, sticky="w", padx=10, pady=(0, 8))

    def _build_ago_tab(self, parent):
        parent.columnconfigure(0, weight=1)
        f = ttk.Frame(parent, style="Panel.TFrame")
        f.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        f.columnconfigure(0, weight=1)
        self._ago_var = tk.StringVar(value="4.54 Ga")
        entry = ttk.Entry(f, textvariable=self._ago_var,
                          font=("Segoe UI", 11), width=18)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda _: self._on_add_click())
        unit_vals = ["années", "milliers (ka)", "millions (Ma)", "milliards (Ga)"]
        self._ago_unit = ttk.Combobox(f, values=unit_vals, state="readonly", width=16)
        self._ago_unit.current(3)
        self._ago_unit.grid(row=0, column=1, padx=(6, 0))
        ttk.Label(parent, text="Ex : 4.54  ·  4 540 000 000  ·  4,54Ga  ·  4.54 billion",
                  style="Muted.TLabel").grid(row=1, column=0, padx=8, pady=(0, 6), sticky="w")

    def _build_date_tab(self, parent):
        # Mirror the layout of the "Il y a…" tab: a sub-frame with ttk.Entry widgets.
        parent.columnconfigure(0, weight=1)
        wrap = ttk.Frame(parent, style="Panel.TFrame")
        wrap.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        wrap.columnconfigure(1, weight=0)

        rows = [
            ("Année",   "_year_var",  12, "1969",  "négatif = avant J.-C."),
            ("Mois",    "_month_var",  6, "1",     "1 – 12"),
            ("Jour",    "_day_var",    6, "1",     "1 – 31"),
            ("Heure",   "_hour_var",   6, "0",     "0 – 23"),
            ("Minute",  "_min_var",    6, "0",     "0 – 59"),
            ("Seconde", "_sec_var",    6, "0",     "0 – 59"),
        ]
        for i, (label, attr, w, default, hint) in enumerate(rows):
            ttk.Label(wrap, text=label + " :", style="Muted.TLabel").grid(
                row=i, column=0, sticky="w", padx=(0, 8), pady=3)
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            entry = ttk.Entry(wrap, textvariable=var, width=w,
                               font=("Segoe UI", 10))
            entry.grid(row=i, column=1, sticky="w", pady=3)
            if hint:
                ttk.Label(wrap, text="  " + hint,
                          style="Muted.TLabel").grid(
                    row=i, column=2, sticky="w", padx=(8, 0))

    # ── Description helpers ──────────────────────────────────────────────────
    def _get_description(self) -> str:
        return self._desc_text.get("1.0", "end").strip()

    def _set_description(self, text: str):
        self._desc_text.delete("1.0", "end")
        if text:
            self._desc_text.insert("1.0", text)

    def refresh_tag_choices(self):
        # Single-group selection via a combobox; values may be hierarchical
        # labels (« Parent ▸ Enfant »).
        if not hasattr(self, "_group_combo"):
            return
        prev_leaf = (self._group_var.get() or "").rsplit(" ▸ ", 1)[-1].strip() \
                    or "Non-classés"
        choices = list(self.tag_names_provider())
        self._group_combo.configure(values=choices)
        # Re-select the same leaf, keeping the new hierarchical prefix.
        match = next((c for c in choices
                      if c.rsplit(" ▸ ", 1)[-1].strip() == prev_leaf), None)
        self._group_var.set(match or "Non-classés")

    def _selected_group_name(self) -> str:
        # Strip the « Parent ▸ » prefix added by hierarchical labels.
        raw = self._group_var.get() or "Non-classés"
        return raw.rsplit(" ▸ ", 1)[-1].strip() or "Non-classés"

    def _reset_tag_selection(self):
        self._group_var.set("Non-classés")

    def _reset_inputs(self):
        self._name_var.set("")
        self._set_description("")
        self._reset_tag_selection()
        if hasattr(self, "_period_ongoing_var"):
            self._period_ongoing_var.set(False)
            self._on_period_ongoing_change()

    def _build_period_tab(self, parent):
        parent.columnconfigure(0, weight=1)

        # ── Mode toggle ───────────────────────────────────────────────────────
        mode = ttk.Frame(parent, style="Panel.TFrame")
        mode.grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))
        ttk.Label(mode, text="Saisie :",
                  style="Muted.TLabel").pack(side="left", padx=(0, 8))
        self._period_mode_var = tk.StringVar(value="date")
        ttk.Radiobutton(mode, text="Date / Heure",
                         variable=self._period_mode_var, value="date",
                         command=self._on_period_mode_change).pack(side="left", padx=(0, 8))
        ttk.Radiobutton(mode, text="Il y a…",
                         variable=self._period_mode_var, value="ago",
                         command=self._on_period_mode_change).pack(side="left")

        # ── Ongoing toggle ────────────────────────────────────────────────────
        self._period_ongoing_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            parent, text="En cours (la fin est « maintenant », automatique)",
            variable=self._period_ongoing_var,
            command=self._on_period_ongoing_change,
            bg=PALETTE["panel"], fg=PALETTE["text"],
            activebackground=PALETTE["panel"],
            activeforeground=PALETTE["text"],
            selectcolor=PALETTE["entry"], highlightthickness=0,
            font=("Segoe UI", 9)).grid(
            row=1, column=0, sticky="w", padx=8, pady=(0, 4))

        # ── Container that swaps date / ago panels ────────────────────────────
        container = ttk.Frame(parent, style="Panel.TFrame")
        container.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        container.columnconfigure(0, weight=1)

        self._period_date_panel = ttk.Frame(container, style="Panel.TFrame")
        self._period_date_panel.grid(row=0, column=0, sticky="ew")
        self._build_period_date_panel(self._period_date_panel)

        self._period_ago_panel = ttk.Frame(container, style="Panel.TFrame")
        self._period_ago_panel.grid(row=0, column=0, sticky="ew")
        self._build_period_ago_panel(self._period_ago_panel)
        self._period_ago_panel.grid_remove()

    def _build_period_date_panel(self, parent):
        for col, title in enumerate(("Début", "Fin")):
            ttk.Label(parent, text=title, style="Section.TLabel").grid(
                row=0, column=col * 2, columnspan=2, sticky="w",
                padx=(0 if col == 0 else 14, 0), pady=(0, 4))
        rows = [
            ("Année",   "year",  "1939", "1945", 8),
            ("Mois",    "month", "1",    "1",    4),
            ("Jour",    "day",   "1",    "1",    4),
            ("Heure",   "hour",  "0",    "0",    4),
            ("Minute",  "min",   "0",    "0",    4),
            ("Seconde", "sec",   "0",    "0",    4),
        ]
        for i, (label, prefix, ds, de, w) in enumerate(rows):
            for col, default in enumerate((ds, de)):
                px = (0 if col == 0 else 14, 0)
                ttk.Label(parent, text=label + " :",
                          style="Muted.TLabel").grid(
                    row=1 + i, column=col * 2, sticky="w", padx=px, pady=2)
                var = tk.StringVar(value=default)
                setattr(self,
                         f"_period_{'start' if col == 0 else 'end'}_{prefix}_var",
                         var)
                ttk.Entry(parent, textvariable=var, width=w,
                           font=("Segoe UI", 10)).grid(
                    row=1 + i, column=col * 2 + 1, sticky="w", pady=2)

    def _build_period_ago_panel(self, parent):
        units = ["années", "milliers (ka)", "millions (Ma)", "milliards (Ga)"]
        for col, title in enumerate(("Début (le + ancien)", "Fin (le + récent)")):
            ttk.Label(parent, text=title, style="Section.TLabel").grid(
                row=0, column=col * 2, columnspan=2, sticky="w",
                padx=(0 if col == 0 else 14, 0), pady=(0, 4))

        for col, default_val in enumerate(("201.4", "145")):
            px = (0 if col == 0 else 14, 0)
            ttk.Label(parent, text="Valeur :",
                      style="Muted.TLabel").grid(
                row=1, column=col * 2, sticky="w", padx=px, pady=2)
            var = tk.StringVar(value=default_val)
            setattr(self,
                     f"_period_{'start' if col == 0 else 'end'}_ago_var",
                     var)
            ttk.Entry(parent, textvariable=var, width=10,
                       font=("Segoe UI", 10)).grid(
                row=1, column=col * 2 + 1, sticky="w", pady=2)

            ttk.Label(parent, text="Unité :",
                      style="Muted.TLabel").grid(
                row=2, column=col * 2, sticky="w", padx=px, pady=2)
            unit_combo = ttk.Combobox(parent, values=units,
                                        state="readonly", width=14)
            unit_combo.current(2)   # Ma
            setattr(self,
                     f"_period_{'start' if col == 0 else 'end'}_ago_unit",
                     unit_combo)
            unit_combo.grid(row=2, column=col * 2 + 1, sticky="w", pady=2)

    def _on_period_mode_change(self):
        if self._period_mode_var.get() == "date":
            self._period_ago_panel.grid_remove()
            self._period_date_panel.grid()
        else:
            self._period_date_panel.grid_remove()
            self._period_ago_panel.grid()
        # Re-apply the ongoing greyout if it's checked.
        self._on_period_ongoing_change()

    def _on_period_ongoing_change(self):
        """Disable the « Fin » entries when the period is ongoing."""
        ongoing = self._period_ongoing_var.get()
        # Walk both date and ago panels, find anything attached to *_end_*.
        def set_end_state(panel, state):
            for child in panel.winfo_children():
                # recurse
                set_end_state(child, state)
                # entries / spinboxes / comboboxes → disable
                try:
                    info = child.grid_info()
                except Exception:
                    info = {}
                # By layout convention end fields live on column 2/3 (date)
                # or are sub-widgets attached to *_end_* attributes (ago).
                # Easiest: rely on attribute names we created.
            # set state on widgets we created with the "end" attr names
        for prefix in ("_period_end_year_var", "_period_end_month_var",
                        "_period_end_day_var", "_period_end_hour_var",
                        "_period_end_min_var", "_period_end_sec_var",
                        "_period_end_ago_var"):
            # the var itself isn't a widget; nothing to do here.
            pass
        # Disable Entry / Combobox widgets registered for end fields.
        for w in self._period_end_widgets():
            try:
                w.configure(state=("disabled" if ongoing else "normal"))
            except tk.TclError:
                pass
        # Combobox needs "readonly" instead of "normal".
        for w in self._period_end_combos():
            try:
                w.configure(state=("disabled" if ongoing else "readonly"))
            except tk.TclError:
                pass

    def _period_end_widgets(self):
        """All Entry widgets that hold the « Fin » values (date + ago modes)."""
        out = []
        # Date panel: Entry for year/month/day/hour/min/sec  (column == 3)
        for child in self._period_date_panel.winfo_children():
            try:
                info = child.grid_info()
            except Exception:
                continue
            if info.get("column") == 3 and isinstance(child, ttk.Entry):
                out.append(child)
        # Ago panel: Entry for value, Combobox for unit (column == 3)
        for child in self._period_ago_panel.winfo_children():
            try:
                info = child.grid_info()
            except Exception:
                continue
            if info.get("column") == 3 and isinstance(child, ttk.Entry):
                out.append(child)
        return out

    def _period_end_combos(self):
        out = []
        for child in self._period_ago_panel.winfo_children():
            try:
                info = child.grid_info()
            except Exception:
                continue
            if info.get("column") == 3 and isinstance(child, ttk.Combobox):
                out.append(child)
        return out

    @staticmethod
    def _ago_unit_multiplier(unit_str: str) -> float:
        if "Ga" in unit_str or "milliard" in unit_str: return 1e9
        if "Ma" in unit_str or "million"  in unit_str: return 1e6
        if "ka" in unit_str or "millier"  in unit_str: return 1e3
        return 1.0

    def _on_tab_change(self, _=None):
        is_period = (self._notebook.index("current") == 2)
        self._add_btn_text.set("＋  Ajouter la période" if is_period
                                else "＋  Ajouter l'évènement")

    def _next_color(self) -> str:
        c = EVENT_COLORS[self._color_idx % len(EVENT_COLORS)]
        self._color_idx += 1
        return c

    def get_years_ago(self) -> Optional[float]:
        tab = self._notebook.index("current")
        if tab == 0:
            raw    = self._ago_var.get().strip()
            parsed = parse_years_ago(raw)
            if parsed is not None: return parsed
            try:   num = float(raw.replace(",", ".").replace(" ", ""))
            except ValueError: return None
            unit = self._ago_unit.get()
            if "Ga" in unit or "milliard" in unit: return num * 1e9
            if "Ma" in unit or "million"  in unit: return num * 1e6
            if "ka" in unit or "millier"  in unit: return num * 1e3
            return num
        else:  # tab == 1: Date / Heure
            try:
                return date_to_years_ago(
                    int(self._year_var.get()),
                    int(self._month_var.get()),
                    int(self._day_var.get()),
                    int(self._hour_var.get()),
                    int(self._min_var.get()),
                    int(self._sec_var.get()))
            except (ValueError, AttributeError):
                return None

    def _on_add_click(self):
        self._err_var.set("")
        if self._notebook.index("current") == 2:
            self._on_add_period_click()
            return
        ya = self.get_years_ago()
        if ya is None:
            self._err_var.set("Valeur non reconnue.")
            return
        name = self._name_var.get().strip() or f"Évènement {self._color_idx + 1}"
        self.on_add(name, ya, self._next_color(), self._get_description(),
                    self._selected_group_name())
        self._reset_inputs()

    def _on_add_period_click(self):
        ongoing = bool(self._period_ongoing_var.get())
        if self._period_mode_var.get() == "date":
            try:
                ys = date_to_years_ago(
                    int(self._period_start_year_var.get()),
                    int(self._period_start_month_var.get()),
                    int(self._period_start_day_var.get()),
                    int(self._period_start_hour_var.get()),
                    int(self._period_start_min_var.get()),
                    int(self._period_start_sec_var.get()))
                if ongoing:
                    ye = 0.0
                else:
                    ye = date_to_years_ago(
                        int(self._period_end_year_var.get()),
                        int(self._period_end_month_var.get()),
                        int(self._period_end_day_var.get()),
                        int(self._period_end_hour_var.get()),
                        int(self._period_end_min_var.get()),
                        int(self._period_end_sec_var.get()))
            except (ValueError, AttributeError):
                self._err_var.set("Date de début ou de fin invalide.")
                return
        else:
            try:
                ys_raw = float(self._period_start_ago_var.get()
                                .replace(",", ".").replace(" ", ""))
            except (ValueError, AttributeError):
                self._err_var.set("Valeur 'il y a' (début) invalide.")
                return
            ys = ys_raw * self._ago_unit_multiplier(
                self._period_start_ago_unit.get())
            if ongoing:
                ye = 0.0
            else:
                try:
                    ye_raw = float(self._period_end_ago_var.get()
                                    .replace(",", ".").replace(" ", ""))
                except (ValueError, AttributeError):
                    self._err_var.set("Valeur 'il y a' (fin) invalide.")
                    return
                ye = ye_raw * self._ago_unit_multiplier(
                    self._period_end_ago_unit.get())
        # Ensure ys (start) is older than ye (end). If not, swap (skip if ongoing).
        if not ongoing and ye > ys:
            ys, ye = ye, ys
        if not ongoing and abs(ys - ye) < 1e-9:
            self._err_var.set("Le début et la fin sont identiques.")
            return
        name = self._name_var.get().strip() or f"Période {self._color_idx + 1}"
        self.on_add_period(name, ys, ye, self._next_color(),
                            self._get_description(),
                            self._selected_group_name(),
                            ongoing)
        self._reset_inputs()


# ── Event / Period List Panel ──────────────────────────────────────────────────

class TagPanel(ttk.Frame):
    def __init__(self, parent, on_add_tag, on_toggle_tag,
                 on_bulk_visibility, on_delete_tag,
                 on_set_color, on_export_group, on_edit_tag, **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self.on_add_tag = on_add_tag
        self.on_toggle_tag = on_toggle_tag
        self.on_bulk_visibility = on_bulk_visibility
        self.on_delete_tag = on_delete_tag
        self.on_set_color = on_set_color
        self.on_export_group = on_export_group
        self.on_edit_tag = on_edit_tag
        self._tag_rows: dict[str, tk.Frame] = {}
        self._collapsed_tags: set[str] = set()
        self._last_tags: dict = {}
        self._last_tag_events: list = []
        self._last_tag_periods: list = []
        self._highlighted_tag: Optional[str] = None
        self.columnconfigure(0, weight=1)
        self._build()

    def _build(self):
        ttk.Label(self, text="Groupes",
                  style="Section.TLabel").grid(
            row=0, column=0, sticky="w", padx=10, pady=(10, 4))

        add_row = ttk.Frame(self, style="Panel.TFrame")
        add_row.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))
        add_row.columnconfigure(0, weight=1)
        self._tag_name_var = tk.StringVar()
        ttk.Entry(add_row, textvariable=self._tag_name_var).grid(
            row=0, column=0, sticky="ew", padx=(0, 6))
        ttk.Button(add_row, text="Ajouter", style="Small.TButton",
                   command=self._on_add_tag_click).grid(row=0, column=1)

        # Bulk-visibility toolbar
        bulk = ttk.Frame(self, style="Panel.TFrame")
        bulk.grid(row=2, column=0, sticky="ew", padx=8, pady=(0, 4))
        ttk.Button(bulk, text="Tout cocher", style="Small.TButton",
                   command=lambda: self.on_bulk_visibility("all")).pack(
            side="left", padx=(0, 4))
        ttk.Button(bulk, text="Tout décocher", style="Small.TButton",
                   command=lambda: self.on_bulk_visibility("none")).pack(
            side="left", padx=(0, 4))
        ttk.Button(bulk, text="Inverser", style="Small.TButton",
                   command=lambda: self.on_bulk_visibility("invert")).pack(
            side="left")

        ttk.Label(self,
                  text="Glissez un évènement ou une période ici pour le déplacer "
                       "dans ce groupe. Ctrl+drag pour copier. Cliquez la "
                       "pastille de couleur pour la changer.",
                  style="Muted.TLabel",
                  font=("Segoe UI", 8, "italic"),
                  wraplength=260).grid(
            row=3, column=0, sticky="w", padx=10, pady=(0, 6))

        self._tags_wrap = ttk.Frame(self, style="Panel.TFrame")
        self._tags_wrap.grid(row=4, column=0, sticky="ew", padx=8, pady=(0, 8))
        self._tags_wrap.columnconfigure(0, weight=1)

    def _on_add_tag_click(self):
        name = self._tag_name_var.get().strip()
        # Top-level group (parent_name = None).
        if self.on_add_tag(name, None):
            self._tag_name_var.set("")

    def refresh_tags(self, tags: dict, events: list, periods: list):
        self._last_tags = tags
        self._last_tag_events = events
        self._last_tag_periods = periods
        for child in self._tags_wrap.winfo_children():
            child.destroy()
        self._tag_rows.clear()

        counts: dict[str, int] = {}
        for ev in events:
            counts[ev.group_name] = counts.get(ev.group_name, 0) + 1
        for per in periods:
            counts[per.group_name] = counts.get(per.group_name, 0) + 1

        children_by_parent: dict[str, list[str]] = {}
        for name, tag in tags.items():
            if tag.parent_name:
                children_by_parent.setdefault(tag.parent_name, []).append(name)
        for children in children_by_parent.values():
            children.sort(key=str.lower)
        self._collapsed_tags.intersection_update(
            {name for name in tags if children_by_parent.get(name)})

        # Build the hierarchy: roots (locked default first), each followed by
        # its descendants in tree order. Sub-groups are indented per depth.
        def depth_of(name: str) -> int:
            d, cur, seen = 0, tags.get(name), set()
            while cur and cur.parent_name and cur.parent_name not in seen:
                seen.add(cur.parent_name)
                cur = tags.get(cur.parent_name)
                d += 1
            return d

        def walk(name: str):
            yield name
            if name in self._collapsed_tags:
                return
            for c in children_by_parent.get(name, []):
                yield from walk(c)

        roots = sorted(
            (n for n, t in tags.items() if not t.parent_name),
            key=lambda n: (not tags[n].locked_visible, n.lower()))
        ordered_names = [n for r in roots for n in walk(r)]
        sorted_tags = [(n, tags[n]) for n in ordered_names]

        for row_idx, (tag_name, tag) in enumerate(sorted_tags):
            indent = depth_of(tag_name) * 14    # px per level
            row = tk.Frame(self._tags_wrap, bg=PALETTE["panel2"],
                           highlightthickness=1,
                           highlightbackground=PALETTE["border"])
            row.grid(row=row_idx, column=0, sticky="ew", pady=2)
            # Column layout: 0=swatch (fixed) · 1=title/meta (expands) ·
            # 2=visible toggle · 3+=actions.
            row.grid_columnconfigure(0, weight=0)
            row.grid_columnconfigure(1, weight=1)

            # Color swatch (clickable → opens a color picker).  Fixed pixel
            # width via tk.Frame instead of tk.Label so the pastille is
            # always visible regardless of font metrics.
            color_value = tag.color or "#58a6ff"
            swatch = tk.Frame(row, bg=color_value, width=18, height=18,
                              cursor="hand2", relief="solid", bd=1,
                              highlightthickness=0)
            swatch.grid_propagate(False)
            swatch.grid(row=0, column=0, rowspan=2, sticky="w",
                         padx=(8 + indent, 6), pady=8)
            swatch.bind("<Button-1>",
                         lambda _e, n=tag_name, c=color_value:
                            self._pick_color(n, c))

            title_line = tk.Frame(row, bg=PALETTE["panel2"])
            title_line.grid(row=0, column=1, sticky="w",
                            padx=(0, 8), pady=(6, 0))
            if children_by_parent.get(tag_name):
                collapsed = tag_name in self._collapsed_tags
                tk.Button(title_line, text=("▸" if collapsed else "▾"),
                          bg=PALETTE["panel2"], fg=PALETTE["muted"],
                          activebackground=PALETTE["panel2"],
                          activeforeground=PALETTE["accent"],
                          font=("Segoe UI", 8, "bold"), bd=0,
                          width=2, cursor="hand2",
                          command=lambda n=tag_name:
                              self._toggle_group_collapsed(n)).pack(
                    side="left", padx=(0, 2))
            title = tk.Label(title_line, text=tag_name, bg=PALETTE["panel2"],
                             fg=PALETTE["text"], anchor="w",
                             font=("Segoe UI", 9, "bold"))
            title.pack(side="left")

            meta_parts = [f"{counts.get(tag_name, 0)} element(s)"]
            if tag.locked_visible:
                meta_parts.append("toujours visible")
            meta = tk.Label(row, text="  ·  ".join(meta_parts),
                            bg=PALETTE["panel2"], fg=PALETTE["muted"],
                            anchor="w", font=("Segoe UI", 8))
            meta.grid(row=1, column=1, sticky="w", padx=(0, 8), pady=(0, 6))

            visible_var = tk.BooleanVar(value=(True if tag.locked_visible
                                               else tag.visible))
            chk = tk.Checkbutton(
                row, text="Visible", variable=visible_var,
                command=lambda n=tag_name, v=visible_var: self.on_toggle_tag(n, v.get()),
                bg=PALETTE["panel2"], fg=PALETTE["text"],
                activebackground=PALETTE["panel2"],
                activeforeground=PALETTE["text"],
                selectcolor=PALETTE["entry"], highlightthickness=0,
                disabledforeground=PALETTE["muted"])
            if tag.locked_visible:
                chk.configure(state="disabled")
            chk.grid(row=0, column=2, rowspan=2, sticky="e", padx=(8, 0))

            # Add-subgroup button — creates a child group under this one.
            tk.Button(row, text="＋", bg=PALETTE["panel2"],
                      fg=PALETTE["muted"],
                      activebackground=PALETTE["panel2"],
                      activeforeground=PALETTE["accent"],
                      font=("Segoe UI", 9, "bold"), bd=0, cursor="hand2",
                      command=lambda n=tag_name: self._prompt_subgroup(n)).grid(
                row=0, column=3, rowspan=2, sticky="e", padx=(4, 0))

            # Export button — saves only this group's items to a .events file.
            tk.Button(row, text="💾", bg=PALETTE["panel2"],
                      fg=PALETTE["muted"],
                      activebackground=PALETTE["panel2"],
                      activeforeground=PALETTE["accent"],
                      font=("Segoe UI", 9), bd=0, cursor="hand2",
                      command=lambda n=tag_name: self.on_export_group(n)).grid(
                row=0, column=4, rowspan=2, sticky="e", padx=(4, 0))

            # Edit button — rename the group or move it under another parent.
            if not tag.locked_visible:
                tk.Button(row, text="✎", bg=PALETTE["panel2"],
                          fg=PALETTE["muted"],
                          activebackground=PALETTE["panel2"],
                          activeforeground=PALETTE["accent"],
                          font=("Segoe UI", 9), bd=0, cursor="hand2",
                          command=lambda n=tag_name, ts=tags:
                              self._prompt_edit_group(
                                  n, ts, self.winfo_pointerx(),
                                  self.winfo_pointery())).grid(
                    row=0, column=5, rowspan=2, sticky="e", padx=(4, 0))

            # Delete button — hidden on the locked default tag.
            if not tag.locked_visible:
                tk.Button(row, text="✕", bg=PALETTE["panel2"],
                          fg=PALETTE["muted"],
                          activebackground=PALETTE["panel2"],
                          activeforeground=PALETTE["accent2"],
                          font=("Segoe UI", 9), bd=0, cursor="hand2",
                          command=lambda n=tag_name: self.on_delete_tag(n)).grid(
                    row=0, column=6, rowspan=2, sticky="e", padx=(4, 8))

            self._tag_rows[tag_name] = row

    def _toggle_group_collapsed(self, tag_name: str):
        if tag_name in self._collapsed_tags:
            self._collapsed_tags.remove(tag_name)
        else:
            self._collapsed_tags.add(tag_name)
        self.refresh_tags(
            getattr(self, "_last_tags", {}),
            getattr(self, "_last_tag_events", []),
            getattr(self, "_last_tag_periods", []))

    def _prompt_edit_group(self, tag_name: str, tags: dict,
                           x_root: Optional[int] = None,
                           y_root: Optional[int] = None):
        """Edit a group's name and parent while preventing hierarchy cycles."""
        tag = tags.get(tag_name)
        if tag is None or tag.locked_visible:
            return

        def descendants_of(name: str) -> set[str]:
            out = set()
            for child_name, child in tags.items():
                if child.parent_name == name:
                    out.add(child_name)
                    out.update(descendants_of(child_name))
            return out

        def ancestors_of(name: str) -> list[str]:
            out, cur, seen = [], name, set()
            while cur and cur in tags and cur not in seen:
                seen.add(cur)
                out.append(cur)
                cur = tags[cur].parent_name
            return out

        def label_for(name: str) -> str:
            ancestors = ancestors_of(name)[1:]
            if ancestors:
                return " ▸ ".join(reversed(ancestors)) + " ▸ " + name
            return name

        forbidden = {tag_name, *descendants_of(tag_name)}
        parent_names = sorted(
            (n for n in tags if n not in forbidden),
            key=lambda n: label_for(n).lower())

        none_label = "(aucun parent)"
        label_to_parent = {none_label: None}
        for name in parent_names:
            label_to_parent[label_for(name)] = name

        win = tk.Toplevel(self)
        win.title("Modifier le groupe")
        win.configure(bg=PALETTE["bg"])
        win.transient(self)
        win.grab_set()
        win.resizable(False, False)
        win.bind("<Escape>", lambda _e: win.destroy())

        outer = ttk.Frame(win, style="Panel.TFrame")
        outer.pack(fill="both", expand=True, padx=2, pady=2)
        ttk.Label(outer, text="Modifier le groupe",
                  style="Section.TLabel").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=12, pady=(12, 8))

        ttk.Label(outer, text="Nom :", style="Muted.TLabel").grid(
            row=1, column=0, sticky="w", padx=(12, 6), pady=4)
        name_var = tk.StringVar(value=tag_name)
        ttk.Entry(outer, textvariable=name_var, width=38).grid(
            row=1, column=1, sticky="ew", padx=(0, 12), pady=4)

        ttk.Label(outer, text="Parent :", style="Muted.TLabel").grid(
            row=2, column=0, sticky="w", padx=(12, 6), pady=4)
        current_parent_label = none_label
        if tag.parent_name in tags:
            current_parent_label = label_for(tag.parent_name)
        parent_var = tk.StringVar(value=current_parent_label)
        ttk.Combobox(outer, textvariable=parent_var,
                     values=list(label_to_parent.keys()),
                     state="readonly", width=36).grid(
            row=2, column=1, sticky="ew", padx=(0, 12), pady=4)

        btns = ttk.Frame(outer, style="Panel.TFrame")
        btns.grid(row=3, column=0, columnspan=2, sticky="e", padx=12, pady=12)
        ttk.Button(btns, text="Annuler", style="Small.TButton",
                   command=win.destroy).pack(side="right", padx=(6, 0))

        def save():
            parent_name = label_to_parent.get(parent_var.get())
            if self.on_edit_tag(tag_name, name_var.get(), parent_name):
                win.destroy()

        ttk.Button(btns, text="Enregistrer", style="Accent.TButton",
                   command=save).pack(side="right")

        win.update_idletasks()
        try:
            w, h = win.winfo_width(), win.winfo_height()
            screen_w = win.winfo_screenwidth()
            screen_h = win.winfo_screenheight()
            x = (x_root if x_root is not None else self.winfo_rootx()) + 12
            y = (y_root if y_root is not None else self.winfo_rooty()) + 12
            x = max(0, min(x, screen_w - w - 20))
            y = max(0, min(y, screen_h - h - 60))
            win.geometry(f"+{x}+{y}")
        except Exception:
            pass
        win.lift()
        win.focus_force()

    def _prompt_subgroup(self, parent_name: str):
        """Ask the user for a name and create a sub-group under `parent_name`."""
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "Nouveau sous-groupe",
            f"Nom du sous-groupe sous « {parent_name} » :",
            parent=self)
        if name and name.strip():
            self.on_add_tag(name.strip(), parent_name)

    def _pick_color(self, tag_name: str, current_color: str = "#58a6ff"):
        from tkinter import colorchooser
        chosen = colorchooser.askcolor(color=current_color, parent=self,
                                        title=f"Couleur du groupe « {tag_name} »")
        if chosen and chosen[1]:
            self.on_set_color(tag_name, chosen[1])

        self.set_drop_target(self._highlighted_tag)

    def tag_at_root(self, x_root: int, y_root: int) -> Optional[str]:
        for tag_name, row in self._tag_rows.items():
            x0 = row.winfo_rootx()
            y0 = row.winfo_rooty()
            x1 = x0 + row.winfo_width()
            y1 = y0 + row.winfo_height()
            if x0 <= x_root <= x1 and y0 <= y_root <= y1:
                return tag_name
        return None

    def set_drop_target(self, tag_name: Optional[str]):
        self._highlighted_tag = tag_name
        def set_bg(widget, bg):
            for child in widget.winfo_children():
                if isinstance(child, tk.Checkbutton):
                    child.configure(bg=bg, activebackground=bg)
                elif isinstance(child, (tk.Label, tk.Frame)):
                    child.configure(bg=bg)
                    set_bg(child, bg)
                elif isinstance(child, tk.Button):
                    child.configure(bg=bg, activebackground=bg)
        for name, row in self._tag_rows.items():
            bg = PALETTE["hover"] if name == tag_name else PALETTE["panel2"]
            border = PALETTE["accent"] if name == tag_name else PALETTE["border"]
            row.configure(bg=bg, highlightbackground=border)
            set_bg(row, bg)


class EventListPanel(ttk.Frame):
    """
    Right-side scrollable list of events and periods.
    Right-click → Modifier / Supprimer.  Double-click → focus on the timeline.
    """

    def __init__(self, parent, on_remove, on_remove_period,
                 on_edit_event, on_edit_period,
                 on_focus_event, on_focus_period, on_clear,
                 on_begin_drag, on_filter_change, **kwargs):
        super().__init__(parent, style="Panel.TFrame", **kwargs)
        self.on_remove         = on_remove
        self.on_remove_period  = on_remove_period
        self.on_edit_event     = on_edit_event
        self.on_edit_period    = on_edit_period
        self.on_focus_event    = on_focus_event
        self.on_focus_period   = on_focus_period
        self.on_clear          = on_clear
        self.on_begin_drag     = on_begin_drag
        self.on_filter_change  = on_filter_change
        self.columnconfigure(0, weight=1)
        self.rowconfigure(4, weight=1)
        self._build()

    def _build(self):
        hdr = ttk.Frame(self, style="Panel.TFrame")
        hdr.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 2))
        hdr.columnconfigure(0, weight=1)
        ttk.Label(hdr, text="Évènements ajoutés",
                  style="Section.TLabel").grid(row=0, column=0, sticky="w")

        ttk.Label(self,
                  text="Clic-droit : modifier / supprimer  ·  "
                       "Double-clic : centrer dans la timeline",
                  style="Muted.TLabel",
                  font=("Segoe UI", 8, "italic")).grid(
            row=1, column=0, sticky="w", padx=10, pady=(0, 4))

        # Filter dropdown: "Tout" or a specific group name.
        flt = ttk.Frame(self, style="Panel.TFrame")
        flt.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 4))
        flt.columnconfigure(1, weight=1)
        ttk.Label(flt, text="Afficher :", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", padx=(0, 8))
        self._filter_var = tk.StringVar(value="Tout")
        # `_filter_choice_combo` is rebuilt by the app when the group list
        # changes — see `set_group_choices()` below.
        self._filter_choice_combo = ttk.Combobox(
            flt, textvariable=self._filter_var, state="readonly",
            values=["Tout"])
        self._filter_choice_combo.grid(row=0, column=1, sticky="ew")
        self._filter_choice_combo.bind(
            "<<ComboboxSelected>>",
            lambda _: self.on_filter_change(self._filter_var.get()))

        # Live search by name — narrows the list as the user types.
        search_row = ttk.Frame(self, style="Panel.TFrame")
        search_row.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 4))
        search_row.columnconfigure(1, weight=1)
        ttk.Label(search_row, text="🔎", style="Muted.TLabel").grid(
            row=0, column=0, padx=(0, 4))
        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._on_search_change())
        ttk.Entry(search_row, textvariable=self._search_var).grid(
            row=0, column=1, sticky="ew")
        self._clear_search_btn = tk.Button(
            search_row, text="✕", bg=PALETTE["panel"], fg=PALETTE["muted"],
            font=("Segoe UI", 8), bd=0, cursor="hand2",
            command=lambda: self._search_var.set(""))
        self._clear_search_btn.grid(row=0, column=2, padx=(4, 0))
        # Keep last data for re-filtering on search updates.
        self._last_events: list = []
        self._last_periods: list = []
        self._last_visible_groups = None

        container = ttk.Frame(self, style="Panel.TFrame")
        container.grid(row=4, column=0, sticky="nsew", padx=8, pady=(0, 8))
        container.columnconfigure(0, weight=1)
        container.rowconfigure(0, weight=1)

        self._list_canvas = tk.Canvas(container, bg=PALETTE["panel"],
                                        highlightthickness=0)
        sb = ttk.Scrollbar(container, orient="vertical",
                            command=self._list_canvas.yview)
        self._list_frame = ttk.Frame(self._list_canvas, style="Panel.TFrame")
        self._list_frame.columnconfigure(0, weight=1)
        self._list_window = self._list_canvas.create_window(
            (0, 0), window=self._list_frame, anchor="nw")

        self._list_canvas.configure(yscrollcommand=sb.set)
        self._list_canvas.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")

        self._list_frame.bind(
            "<Configure>",
            lambda _: self._list_canvas.configure(
                scrollregion=self._list_canvas.bbox("all")))
        self._list_canvas.bind(
            "<Configure>",
            lambda e: self._list_canvas.itemconfig(
                self._list_window, width=e.width))
        # Mousewheel scroll only while hovering over the list.
        def _scroll(e):
            self._list_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        self._list_canvas.bind("<Enter>",
            lambda _: self._list_canvas.bind_all("<MouseWheel>", _scroll))
        self._list_canvas.bind("<Leave>",
            lambda _: self._list_canvas.unbind_all("<MouseWheel>"))

    # ── Row interactions ──────────────────────────────────────────────────────

    def _bind_row_actions(self, widget, kind: str, idx: int, label: str):
        """Right-click = context menu, double-click = focus on timeline."""
        def show(event):
            menu = tk.Menu(self, tearoff=0,
                            bg=PALETTE["panel2"], fg=PALETTE["text"],
                            activebackground=PALETTE["accent"],
                            activeforeground="#0d1117",
                            bd=0, font=("Segoe UI", 9))
            if kind == "event":
                menu.add_command(label="Centrer dans la timeline",
                                  command=lambda: self.on_focus_event(idx))
                menu.add_command(label="Modifier…",
                                  command=lambda: self.on_edit_event(idx))
                menu.add_separator()
                menu.add_command(label="Supprimer",
                                  command=lambda: self.on_remove(idx))
            else:
                menu.add_command(label="Centrer dans la timeline",
                                  command=lambda: self.on_focus_period(idx))
                menu.add_command(label="Modifier…",
                                  command=lambda: self.on_edit_period(idx))
                menu.add_separator()
                menu.add_command(label="Supprimer",
                                  command=lambda: self.on_remove_period(idx))
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        def dbl_click(_):
            if kind == "event": self.on_focus_event(idx)
            else:               self.on_focus_period(idx)

        def start_drag(event):
            self.on_begin_drag(kind, idx, label, event)

        def attach(w):
            w.bind("<Button-3>", show)
            w.bind("<Double-Button-1>", dbl_click)
            if not isinstance(w, tk.Button):
                w.bind("<ButtonPress-1>", start_drag)
            for child in w.winfo_children():
                attach(child)
        attach(widget)

    # Special filter values exposed in the combo on top of group names.
    FILTER_ALL     = "Tout"
    FILTER_VISIBLE = "Groupes visibles"

    def set_group_choices(self, group_names: list[str],
                           descendants_map: Optional[dict] = None):
        """Update the filter combo with the live list of groups.

        `group_names` may contain hierarchical labels (« Parent ▸ Enfant »).
        `descendants_map` maps each leaf group name to the set of itself
        plus every descendant — used so that picking a parent in the filter
        shows all items under it, including those of its children.
        """
        previous = self._filter_var.get()
        choices = [self.FILTER_ALL, self.FILTER_VISIBLE, *group_names]
        self._filter_choice_combo.configure(values=choices)
        if previous in choices:
            self._filter_var.set(previous)
        else:
            self._filter_var.set(self.FILTER_ALL)
        self._descendants_map = descendants_map or {}

    @staticmethod
    def _label_to_leaf(label: str) -> str:
        return label.rsplit(" ▸ ", 1)[-1].strip()

    def _on_search_change(self):
        self.refresh_list(self._last_events, self._last_periods,
                           self._last_visible_groups)

    def refresh_list(self, events: list, periods: list,
                      visible_groups=None):
        """
        Always called with the FULL events/periods lists; the panel decides
        what to display based on its own filter mode and search box.
        `visible_groups` is the set of group names currently set "visible";
        used only when filter mode is « groups ».  Indices captured for each
        row remain master-list indices so on_remove / on_edit / on_focus
        target the correct item.
        """
        self._last_events  = events
        self._last_periods = periods
        self._last_visible_groups = visible_groups

        for w in self._list_frame.winfo_children():
            w.destroy()

        query = (self._search_var.get().strip().lower()
                 if hasattr(self, "_search_var") else "")

        def matches(name: str) -> bool:
            return query in name.lower()

        # First filter by the chosen group, keeping master-list indices intact.
        # Filter values: "Tout" (no filter), "Groupes visibles" (union of
        # currently-visible groups from the left panel), or a hierarchical
        # group label.  Picking a parent shows it AND all its descendants.
        chosen = (self._filter_var.get()
                  if hasattr(self, "_filter_var") else self.FILTER_ALL)
        if chosen == self.FILTER_VISIBLE and visible_groups is not None:
            allowed = visible_groups
        elif chosen and chosen not in (self.FILTER_ALL, self.FILTER_VISIBLE):
            leaf = self._label_to_leaf(chosen)
            dmap = getattr(self, "_descendants_map", None) or {}
            allowed = dmap.get(leaf, {leaf})
        else:
            allowed = None

        if allowed is None:
            evt_pairs = list(enumerate(events))
            per_pairs = list(enumerate(periods))
        else:
            evt_pairs = [(i, e) for i, e in enumerate(events)
                          if e.group_name in allowed]
            per_pairs = [(i, p) for i, p in enumerate(periods)
                          if p.group_name in allowed]

        # Then apply the live name filter on top.
        filtered_events  = [(i, e) for (i, e) in evt_pairs if matches(e.name)]
        filtered_periods = [(i, p) for (i, p) in per_pairs if matches(p.name)]

        if not filtered_events and not filtered_periods:
            empty = ("(aucun évènement ni période)" if not query
                     else f"(aucun résultat pour « {query} »)")
            ttk.Label(self._list_frame, text=empty,
                      style="Muted.TLabel").pack(padx=8, pady=6)
            return

        # ── Events section ────────────────────────────────────────────────────
        if filtered_events:
            ttk.Label(self._list_frame, text="Évènements",
                      style="Muted.TLabel",
                      foreground=PALETTE["accent"]).pack(
                anchor="w", padx=6, pady=(2, 0))
            sorted_events = sorted(filtered_events, key=lambda p: p[1].fraction)
            for (real_idx, ev) in sorted_events:
                row = ttk.Frame(self._list_frame, style="Panel.TFrame")
                row.pack(fill="x", padx=4, pady=1)
                row.columnconfigure(1, weight=1)
                dot = tk.Canvas(row, width=10, height=10, bg=PALETTE["panel"],
                                 highlightthickness=0)
                dot.create_oval(1, 1, 9, 9, fill=ev.color, outline="")
                dot.grid(row=0, column=0, padx=(2, 4), pady=2)
                tk.Label(row, text=ev.name, bg=PALETTE["panel"], fg=ev.color,
                         font=("Segoe UI", 9, "bold"), anchor="w").grid(
                    row=0, column=1, sticky="w")
                parts = ev.result_str.split("\n") if ev.result_str else []
                detail_lines = []
                if parts:
                    detail_lines.extend(parts[:2])
                detail_lines.append(f"Groupe : {ev.group_name}")
                ttk.Label(row, text="\n".join(detail_lines), style="Muted.TLabel",
                          justify="left").grid(row=1, column=1, sticky="w")
                tk.Button(row, text="✕", bg=PALETTE["panel"], fg=PALETTE["muted"],
                          font=("Segoe UI", 8), bd=0, cursor="hand2",
                          command=lambda idx=real_idx: self.on_remove(idx)).grid(
                    row=0, column=2, rowspan=2, padx=(4, 2))
                self._bind_row_actions(row, "event", real_idx, ev.name)

        # ── Periods section ───────────────────────────────────────────────────
        if filtered_periods:
            ttk.Label(self._list_frame, text="Périodes",
                      style="Muted.TLabel",
                      foreground=PALETTE["accent"]).pack(
                anchor="w", padx=6, pady=(8, 0))
            sorted_periods = sorted(filtered_periods,
                                     key=lambda p: p[1].fraction_start)
            for (real_idx, p) in sorted_periods:
                row = ttk.Frame(self._list_frame, style="Panel.TFrame")
                row.pack(fill="x", padx=4, pady=1)
                row.columnconfigure(1, weight=1)
                bar = tk.Canvas(row, width=10, height=10, bg=PALETTE["panel"],
                                 highlightthickness=0)
                bar.create_rectangle(1, 4, 9, 6, fill=p.color, outline="")
                bar.grid(row=0, column=0, padx=(2, 4), pady=2)
                title_text = p.name + ("  (en cours)"
                                        if getattr(p, "is_ongoing", False) else "")
                tk.Label(row, text=title_text, bg=PALETTE["panel"], fg=p.color,
                         font=("Segoe UI", 9, "bold"), anchor="w").grid(
                    row=0, column=1, sticky="w")
                sp = p.start_str.split("\n") if p.start_str else []
                ongoing = getattr(p, "is_ongoing", False)
                if ongoing:
                    date_line = f"{sp[0] if sp else ''}  →  en cours"
                    time_line = (f"{sp[1] if len(sp) > 1 else ''}"
                                  if len(sp) > 1 else "")
                else:
                    ep = p.end_str.split("\n") if p.end_str else []
                    date_line = (f"{sp[0] if sp else ''}  →  "
                                  f"{ep[0] if ep else ''}"
                                  if (sp or ep) else "")
                    time_line = ""
                    if len(sp) > 1 or len(ep) > 1:
                        s_t = sp[1] if len(sp) > 1 else ""
                        e_t = ep[1] if len(ep) > 1 else ""
                        time_line = f"{s_t}  →  {e_t}"
                detail_lines = [l for l in (date_line, time_line,
                                              f"Durée : {p.duration_str}",
                                              f"Groupe : {p.group_name}") if l]
                ttk.Label(row, text="\n".join(detail_lines),
                          style="Muted.TLabel",
                          justify="left").grid(row=1, column=1, sticky="w")
                tk.Button(row, text="✕", bg=PALETTE["panel"], fg=PALETTE["muted"],
                          font=("Segoe UI", 8), bd=0, cursor="hand2",
                          command=lambda idx=real_idx: self.on_remove_period(idx)).grid(
                    row=0, column=2, rowspan=2, padx=(4, 2))
                self._bind_row_actions(row, "period", real_idx, p.name)


# ── Main Application ───────────────────────────────────────────────────────────

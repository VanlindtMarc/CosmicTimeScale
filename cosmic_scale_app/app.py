import json
from pathlib import Path
from typing import Optional
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core.shared import (
    ASTRO_YEAR_SECONDS,
    AUTOSAVE_PATH,
    EVENT_COLORS,
    FILE_TYPES,
    PALETTE,
    REFERENCE_PERIODS,
    SECONDS_PER_YEAR,
    TARGET_SCALES,
    CosmicEvent,
    CosmicPeriod,
    CosmicTag,
    child_default_color,
    color_variant_for,
    format_duration_seconds,
    format_result,
    fraction_to_position,
    iso_to_years_ago,
    years_ago_to_iso,
)
from .ui.panels import EditDialog, EventInputPanel, EventListPanel, TagPanel
from .ui.timeline import ZoomableTimeline


class CosmicScaleApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Cosmic Time Scale")
        self.configure(bg=PALETTE["bg"])
        # Fix 1: force dark colors on the combobox dropdown listbox (Windows ignores ttk styles for it)
        self.option_add("*TCombobox*Listbox.background",       PALETTE["entry"])
        self.option_add("*TCombobox*Listbox.foreground",       PALETTE["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", PALETTE["accent"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#0d1117")
        self.minsize(900, 620)
        self.geometry("1150x730")
        self._events:  list[CosmicEvent]  = []
        self._periods: list[CosmicPeriod] = []
        self._tags: dict[str, CosmicTag] = {
            "Non-classés": CosmicTag("Non-classés", visible=True, locked_visible=True)
        }
        self._drag_payload: Optional[dict] = None
        self._drag_window = None
        self._drag_label = None
        # Either "Tout" (show everything) or a specific group name.
        self._list_filter_mode: str = "Tout"
        self._build_styles()
        self._build_ui()
        self._tag_panel.refresh_tags(self._tags, self._events, self._periods)
        self.bind_all("<B1-Motion>", self._on_global_drag_motion, add="+")
        self.bind_all("<ButtonRelease-1>", self._on_global_drag_release, add="+")

    def _build_styles(self):
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure("TFrame",         background=PALETTE["bg"])
        st.configure("Panel.TFrame",   background=PALETTE["panel"])
        st.configure("TLabel",         background=PALETTE["bg"],
                     foreground=PALETTE["text"], font=("Segoe UI", 10))
        st.configure("Title.TLabel",   background=PALETTE["bg"],
                     foreground=PALETTE["accent"], font=("Segoe UI", 16, "bold"))
        st.configure("Section.TLabel", background=PALETTE["panel"],
                     foreground=PALETTE["accent"], font=("Segoe UI", 10, "bold"))
        st.configure("Muted.TLabel",   background=PALETTE["panel"],
                     foreground=PALETTE["muted"], font=("Segoe UI", 9))
        st.configure("TCombobox",      fieldbackground=PALETTE["entry"],
                     background=PALETTE["entry"], foreground=PALETTE["text"],
                     selectbackground=PALETTE["accent"], arrowcolor=PALETTE["accent"])
        # Readonly comboboxes have their own state mapping that overrides the base config.
        st.map("TCombobox",
               fieldbackground=[("readonly", PALETTE["entry"]),
                                ("disabled", PALETTE["panel"])],
               foreground=[("readonly", PALETTE["text"]),
                           ("disabled", PALETTE["muted"])],
               background=[("readonly", PALETTE["entry"]),
                           ("active",   PALETTE["entry"])],
               selectbackground=[("readonly", PALETTE["entry"])],
               selectforeground=[("readonly", PALETTE["text"])],
               arrowcolor=[("readonly", PALETTE["accent"]),
                           ("disabled", PALETTE["muted"])])
        st.configure("TEntry",         fieldbackground=PALETTE["entry"],
                     foreground=PALETTE["text"], insertcolor=PALETTE["text"])
        st.configure("TSpinbox",       fieldbackground=PALETTE["entry"],
                     foreground=PALETTE["text"], insertcolor=PALETTE["text"],
                     arrowcolor=PALETTE["accent"])
        st.configure("TNotebook",      background=PALETTE["panel"], tabmargins=[2, 2, 2, 0])
        st.configure("TNotebook.Tab",  background=PALETTE["border"],
                     foreground=PALETTE["muted"], padding=[8, 4],
                     font=("Segoe UI", 9))
        st.map("TNotebook.Tab",
               background=[("selected", PALETTE["panel2"])],
               foreground=[("selected", PALETTE["accent"])])
        st.configure("Accent.TButton", background=PALETTE["accent"],
                     foreground="#0d1117", font=("Segoe UI", 10, "bold"), bd=0)
        st.map("Accent.TButton",
               background=[("active", "#79c0ff"), ("pressed", "#388bfd")])
        st.configure("Small.TButton",  background=PALETTE["border"],
                     foreground=PALETTE["muted"], font=("Segoe UI", 8), padding=[4, 2])
        st.map("Small.TButton",
               background=[("active", PALETTE["hover"])])
        st.configure("TRadiobutton",   background=PALETTE["panel"],
                     foreground=PALETTE["text"],
                     indicatorbackground=PALETTE["entry"],
                     indicatorcolor=PALETTE["entry"],
                     focuscolor=PALETTE["accent"])
        st.map("TRadiobutton",
               background=[("active", PALETTE["panel"]),
                           ("hover",  PALETTE["panel"])],
               foreground=[("disabled", PALETTE["muted"])],
               indicatorbackground=[("selected", PALETTE["accent"]),
                                     ("pressed",  PALETTE["accent"])],
               indicatorcolor=[("selected", PALETTE["accent"]),
                                ("pressed",  PALETTE["accent"])])
        st.configure("TSeparator",     background=PALETTE["border"])
        st.configure("TScrollbar",     background=PALETTE["border"],
                     troughcolor=PALETTE["panel"], arrowcolor=PALETTE["muted"])

    def _build_ui(self):
        # Title bar
        top = ttk.Frame(self)
        top.pack(fill="x", padx=16, pady=(12, 4))
        ttk.Label(top, text="Cosmic Time Scale",
                  style="Title.TLabel").pack(side="left")
        ttk.Label(top,
                  text="  Transposez l'histoire de l'univers sur une période humaine",
                  foreground=PALETTE["muted"], background=PALETTE["bg"],
                  font=("Segoe UI", 9, "italic")).pack(side="left")

        # Visibility toggles for the side columns.
        self._left_visible  = True
        self._right_visible = True
        self._toggle_right_btn = ttk.Button(
            top, text="Cacher la liste ▶", style="Small.TButton",
            command=self._toggle_right_pane)
        self._toggle_right_btn.pack(side="right", padx=(4, 0))
        self._toggle_left_btn = ttk.Button(
            top, text="◀ Cacher les paramètres", style="Small.TButton",
            command=self._toggle_left_pane)
        self._toggle_left_btn.pack(side="right", padx=(4, 0))

        # Body: 3 fixed columns with a 1 / 2 / 1 ratio.
        body = ttk.Frame(self, style="TFrame")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        body.columnconfigure(0, weight=1, uniform="main-columns")
        body.columnconfigure(1, weight=2, uniform="main-columns")
        body.columnconfigure(2, weight=1, uniform="main-columns")
        body.rowconfigure(0, weight=1)
        self._body = body

        # ── Left pane ─────────────────────────────────────────────────────────
        left_shell = ttk.Frame(body, style="Panel.TFrame")
        self._left_shell = left_shell
        left_shell.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left_shell.columnconfigure(0, weight=1)
        left_shell.rowconfigure(0, weight=1)

        left_canvas = tk.Canvas(left_shell, bg=PALETTE["panel"],
                                highlightthickness=0)
        left_scroll = ttk.Scrollbar(left_shell, orient="vertical",
                                    command=left_canvas.yview)
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.grid(row=0, column=0, sticky="nsew")
        left_scroll.grid(row=0, column=1, sticky="ns")

        left = ttk.Frame(left_canvas, style="Panel.TFrame")
        left.columnconfigure(0, weight=1)
        left_window = left_canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind(
            "<Configure>",
            lambda _: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.bind(
            "<Configure>",
            lambda e: left_canvas.itemconfig(left_window, width=e.width))
        def _scroll_left(e):
            left_canvas.yview_scroll(-1 if e.delta > 0 else 1, "units")
        left_canvas.bind("<Enter>",
            lambda _: left_canvas.bind_all("<MouseWheel>", _scroll_left))
        left_canvas.bind("<Leave>",
            lambda _: left_canvas.unbind_all("<MouseWheel>"))

        # File I/O buttons (the ref/target combos now live in the timeline header)
        io_row = ttk.Frame(left, style="Panel.TFrame")
        io_row.grid(row=8, column=0, sticky="ew", padx=8, pady=(8, 4))
        io_row.columnconfigure(0, weight=1)
        io_row.columnconfigure(1, weight=1)
        ttk.Button(io_row, text="📂  Charger…", style="Small.TButton",
                   command=self._import_file).grid(row=0, column=0, sticky="ew", padx=(0, 4))
        ttk.Button(io_row, text="💾  Exporter…", style="Small.TButton",
                   command=self._export_file).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        self._tag_panel = TagPanel(
            left,
            on_add_tag=self._create_tag,
            on_toggle_tag=self._set_tag_visibility,
            on_bulk_visibility=self._set_bulk_tag_visibility,
            on_delete_tag=self._delete_tag,
            on_set_color=self._set_tag_color,
            on_export_group=self._export_group,
            on_edit_tag=self._edit_tag)
        self._tag_panel.grid(row=9, column=0, sticky="ew")

        self._input_panel = EventInputPanel(
            left,
            on_add=self._add_event,
            on_add_period=self._add_period,
            tag_names_provider=self._tag_names_for_ui)
        self._input_panel.grid(row=10, column=0, sticky="ew")

        # ── Centre column (timeline) ─────────────────────────────────────────
        center = ttk.Frame(body, style="Panel.TFrame")
        center.grid(row=0, column=1, sticky="nsew", padx=8)
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)

        ctrl = ttk.Frame(center, style="Panel.TFrame")
        ctrl.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 4))
        ttk.Label(ctrl, text="Timeline", style="Section.TLabel").pack(side="left")

        ttk.Button(ctrl, text="Réinitialiser zoom", style="Small.TButton",
                   command=lambda: self._timeline.reset_zoom()).pack(side="right")

        # Ref period + target scale combos, on the same line as the title.
        ttk.Label(ctrl, text="  Période :", style="Muted.TLabel").pack(side="left")
        self._ref_combo = ttk.Combobox(
            ctrl, values=list(REFERENCE_PERIODS.keys()),
            state="readonly", width=28)
        self._ref_combo.current(0)
        self._ref_combo.pack(side="left", padx=(4, 6))
        self._ref_combo.bind("<<ComboboxSelected>>", self._on_ref_change)

        self._ref_custom = ttk.Entry(ctrl, width=14)
        self._ref_custom.insert(0, "13800000000")
        self._ref_custom.bind("<Return>", lambda _: self._recalculate_all())
        # Custom-duration entry is hidden unless ref_period == "Personnalisé…".
        self._ref_custom_frame = self._ref_custom  # alias for show/hide
        self._ref_custom.pack_forget()

        ttk.Label(ctrl, text="  Échelle :", style="Muted.TLabel").pack(side="left")
        self._tgt_combo = ttk.Combobox(
            ctrl, values=list(TARGET_SCALES.keys()),
            state="readonly", width=22)
        self._tgt_combo.current(1)
        self._tgt_combo.pack(side="left", padx=(4, 6))
        self._tgt_combo.bind("<<ComboboxSelected>>", self._on_tgt_change)

        self._tgt_custom = ttk.Entry(ctrl, width=12)
        self._tgt_custom.insert(0, str(int(SECONDS_PER_YEAR)))
        self._tgt_custom.bind("<Return>", lambda _: self._recalculate_all())
        self._tgt_custom_frame = self._tgt_custom  # alias for show/hide
        self._tgt_custom.pack_forget()

        self._timeline = ZoomableTimeline(center)
        self._timeline.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))

        # Last result strip
        sep = ttk.Separator(center, orient="horizontal")
        sep.grid(row=2, column=0, sticky="ew", padx=10)
        info = ttk.Frame(center, style="Panel.TFrame")
        info.grid(row=3, column=0, sticky="ew", padx=10, pady=(6, 10))
        info.columnconfigure(1, weight=1)
        ttk.Label(info, text="Dernier résultat :",
                  style="Muted.TLabel").grid(row=0, column=0, padx=(0, 8))
        self._last_result_var = tk.StringVar(value="(aucun évènement calculé)")
        tk.Label(info, textvariable=self._last_result_var,
                 bg=PALETTE["panel"], fg=PALETTE["success"],
                 font=("Segoe UI", 11, "bold"), justify="left").grid(
            row=0, column=1, sticky="w")

        # ── Right pane (events / periods list) ────────────────────────────────
        self._list_panel = EventListPanel(
            body,
            on_remove=self._remove_event,
            on_remove_period=self._remove_period,
            on_edit_event=self._edit_event,
            on_edit_period=self._edit_period,
            on_focus_event=self._focus_event,
            on_focus_period=self._focus_period,
            on_clear=self._clear_events,
            on_begin_drag=self._begin_item_drag,
            on_filter_change=self._set_list_filter_mode)
        self._list_panel.grid(row=0, column=2, sticky="nsew", padx=(8, 0))

    # ── Handlers ───────────────────────────────────────────────────────────────

    def _on_ref_change(self, _=None):
        if REFERENCE_PERIODS[self._ref_combo.get()] is None:
            self._ref_custom.pack(side="left", padx=(0, 6),
                                   after=self._ref_combo)
        else:
            self._ref_custom.pack_forget()
        self._recalculate_all()

    def _on_tgt_change(self, _=None):
        if TARGET_SCALES[self._tgt_combo.get()] is None:
            self._tgt_custom.pack(side="left", padx=(0, 6),
                                   after=self._tgt_combo)
        else:
            self._tgt_custom.pack_forget()
        self._recalculate_all()

    def _get_ref_years(self) -> Optional[float]:
        val = REFERENCE_PERIODS.get(self._ref_combo.get())
        if val is not None: return float(val)
        try: return float(self._ref_custom.get().replace(",", "."))
        except ValueError: return None

    def _get_tgt_secs(self) -> Optional[float]:
        val = TARGET_SCALES.get(self._tgt_combo.get())
        if val == "__REALTIME__":
            ref = self._get_ref_years()
            if ref is None:
                return None
            return float(ref) * ASTRO_YEAR_SECONDS
        if val is not None: return float(val)
        try: return float(self._tgt_custom.get().replace(",", "."))
        except ValueError: return None

    def _get_realtime_ref_years(self) -> Optional[float]:
        if TARGET_SCALES.get(self._tgt_combo.get()) == "__REALTIME__":
            return self._get_ref_years()
        return None

    # ── Side-pane visibility toggles ─────────────────────────────────────────

    def _toggle_left_pane(self):
        self._left_visible = not self._left_visible
        if self._left_visible:
            self._left_shell.grid()
            self._body.columnconfigure(0, weight=1, uniform="main-columns")
            self._toggle_left_btn.configure(text="◀ Cacher les paramètres")
        else:
            self._left_shell.grid_remove()
            self._body.columnconfigure(0, weight=0, uniform="")
            self._toggle_left_btn.configure(text="Afficher les paramètres ▶")

    def _toggle_right_pane(self):
        self._right_visible = not self._right_visible
        if self._right_visible:
            self._list_panel.grid()
            self._body.columnconfigure(2, weight=1, uniform="main-columns")
            self._toggle_right_btn.configure(text="Cacher la liste ▶")
        else:
            self._list_panel.grid_remove()
            self._body.columnconfigure(2, weight=0, uniform="")
            self._toggle_right_btn.configure(text="◀ Afficher la liste")

    def _ensure_default_tag(self):
        self._tags["Non-classés"] = CosmicTag(
            "Non-classés", visible=True, locked_visible=True)

    def _migrate_legacy_general_tag(self):
        """Backward-compat: rename the old 'general' tag to 'Non-classés'."""
        had_legacy = "general" in self._tags
        if had_legacy and "Non-classés" not in self._tags:
            tag = self._tags.pop("general")
            tag.name = "Non-classés"
            tag.locked_visible = True
            self._tags["Non-classés"] = tag
        elif had_legacy:
            self._tags.pop("general", None)
        if had_legacy:
            for ev in self._events:
                if ev.group_name == "general":
                    ev.group_name = "Non-classés"
            for p in self._periods:
                if p.group_name == "general":
                    p.group_name = "Non-classés"

    def _ensure_tag_exists(self, tag_name: str):
        name = (tag_name or "Non-classés").strip() or "Non-classés"
        if name not in self._tags:
            self._tags[name] = CosmicTag(name=name, color=self._next_group_color())
        self._ensure_default_tag()
        return name

    def _next_group_color(self) -> str:
        used = {t.color for t in self._tags.values()}
        for c in EVENT_COLORS:
            if c not in used:
                return c
        return EVENT_COLORS[len(self._tags) % len(EVENT_COLORS)]

    def _normalize_group_name(self, raw_name) -> str:
        """Make sure the chosen group exists; return the canonical name."""
        if raw_name is None:
            return self._ensure_tag_exists("Non-classés")
        return self._ensure_tag_exists(str(raw_name))

    # ── Hierarchy helpers ────────────────────────────────────────────────────

    def _tag_ancestors(self, name: str) -> list[str]:
        """Return [name, parent, grandparent, …] until the root (excluding cycles)."""
        out, cur, seen = [], name, set()
        while cur and cur in self._tags and cur not in seen:
            seen.add(cur)
            out.append(cur)
            cur = self._tags[cur].parent_name
        return out

    def _tag_descendants(self, name: str) -> list[str]:
        """All descendants of `name` (depth-first, excludes `name` itself)."""
        out = []
        children = [n for n, t in self._tags.items() if t.parent_name == name]
        for c in children:
            out.append(c)
            out.extend(self._tag_descendants(c))
        return out

    def _tag_depth(self, name: str) -> int:
        return max(0, len(self._tag_ancestors(name)) - 1)

    def _tag_is_effectively_visible(self, name: str) -> bool:
        """A tag is effectively visible only if it AND every ancestor are."""
        for anc in self._tag_ancestors(name):
            t = self._tags.get(anc)
            if not t: return False
            if not (t.visible or t.locked_visible):
                return False
        return True

    def _sorted_tag_tree(self) -> list[str]:
        """Names of all tags in tree-traversal order (parents before children),
        sorted alphabetically at each level."""
        roots = sorted(
            (n for n, t in self._tags.items() if not t.parent_name),
            key=lambda n: (n != "Non-classés", n.lower()))

        def walk(name):
            yield name
            children = sorted(
                (n for n, t in self._tags.items() if t.parent_name == name),
                key=str.lower)
            for c in children:
                yield from walk(c)

        result = []
        for r in roots:
            result.extend(walk(r))
        return result

    def _tag_names_for_ui(self) -> list[str]:
        """Hierarchical labels: « Parent ▸ Enfant » for the input combo."""
        labels = []
        for name in self._sorted_tag_tree():
            ancestors = self._tag_ancestors(name)[1:]   # skip self
            if ancestors:
                prefix = " ▸ ".join(reversed(ancestors)) + " ▸ "
            else:
                prefix = ""
            labels.append(prefix + name)
        return labels

    def _strip_path(self, label: str) -> str:
        """Convert a hierarchical label back to its leaf name."""
        return label.rsplit(" ▸ ", 1)[-1].strip()

    def _create_tag(self, raw_name: str, parent_name: Optional[str] = None) -> bool:
        name = " ".join(raw_name.split())
        if not name:
            return False
        if name in self._tags:
            messagebox.showinfo("Groupe existant",
                                f"Le groupe « {name} » existe déjà.")
            return False
        # Parent must exist and not be the locked default group at root level.
        if parent_name and parent_name in self._tags:
            base = self._tags[parent_name].color
            color = child_default_color(base, name)
        else:
            parent_name = None
            color = self._next_group_color()
        self._tags[name] = CosmicTag(
            name=name, color=color, parent_name=parent_name)
        self._refresh()
        return True

    def _edit_tag(self, old_name: str, raw_name: str,
                  parent_name: Optional[str] = None) -> bool:
        tag = self._tags.get(old_name)
        if tag is None or tag.locked_visible:
            return False

        new_name = " ".join(str(raw_name or "").split())
        if not new_name:
            messagebox.showinfo("Nom invalide",
                                "Le nom du groupe ne peut pas être vide.",
                                parent=self)
            return False
        if new_name != old_name and new_name in self._tags:
            messagebox.showinfo("Groupe existant",
                                f"Le groupe « {new_name} » existe déjà.",
                                parent=self)
            return False

        if parent_name and parent_name not in self._tags:
            parent_name = None
        if parent_name in (old_name, new_name):
            messagebox.showinfo("Parent invalide",
                                "Un groupe ne peut pas être son propre parent.",
                                parent=self)
            return False
        if parent_name in self._tag_descendants(old_name):
            messagebox.showinfo(
                "Parent invalide",
                "Un groupe ne peut pas être déplacé sous l'un de ses sous-groupes.",
                parent=self)
            return False

        # Rebuild the dict so the renamed group keeps its relative position
        # and children/items keep pointing at the renamed group.
        rebuilt: dict[str, CosmicTag] = {}
        for name, current in self._tags.items():
            if name == old_name:
                current.name = new_name
                current.parent_name = parent_name
                rebuilt[new_name] = current
                continue
            if current.parent_name == old_name:
                current.parent_name = new_name
            rebuilt[name] = current
        self._tags = rebuilt

        if new_name != old_name:
            for ev in self._events:
                if ev.group_name == old_name:
                    ev.group_name = new_name
            for per in self._periods:
                if per.group_name == old_name:
                    per.group_name = new_name

        self._apply_group_colors()
        self._refresh()
        return True

    def _set_tag_visibility(self, tag_name: str, visible: bool):
        tag = self._tags.get(tag_name)
        if not tag or tag.locked_visible:
            return
        new_state = bool(visible)
        tag.visible = new_state
        # Cascade DOWN: a parent toggle propagates to every descendant.
        for child_name in self._tag_descendants(tag_name):
            child = self._tags.get(child_name)
            if child is not None and not child.locked_visible:
                child.visible = new_state
        # Cascade UP only on enable: re-checking a sub-group must also
        # re-check every ancestor so the cascade-visibility rule actually
        # makes the items show.  Disabling a sub-group never touches
        # ancestors (siblings may still need them visible).
        if new_state:
            for anc in self._tag_ancestors(tag_name)[1:]:
                anc_tag = self._tags.get(anc)
                if anc_tag is not None and not anc_tag.locked_visible:
                    anc_tag.visible = True
        self._refresh_visibility_only()

    def _set_tag_color(self, tag_name: str, color: str):
        tag = self._tags.get(tag_name)
        if tag is None: return
        tag.color = color
        self._apply_group_colors()
        self._refresh()

    def _apply_group_colors(self):
        """Recompute every event/period's display color from its group."""
        for ev in self._events:
            base = self._tags[ev.group_name].color \
                   if ev.group_name in self._tags else "#58a6ff"
            ev.color = color_variant_for(base, ev.name)
        for p in self._periods:
            base = self._tags[p.group_name].color \
                   if p.group_name in self._tags else "#58a6ff"
            p.color = color_variant_for(base, p.name)

    def _delete_tag(self, tag_name: str):
        tag = self._tags.get(tag_name)
        if tag is None or tag.locked_visible:
            return
        # Count items in *this* group plus all descendants for the warning.
        affected_groups = {tag_name, *self._tag_descendants(tag_name)}
        n = sum(1 for ev in self._events  if ev.group_name in affected_groups) \
          + sum(1 for p  in self._periods if p.group_name in affected_groups)
        sub_count = len(affected_groups) - 1
        sub_msg = (f"\n{sub_count} sous-groupe(s) seront aussi supprimés."
                   if sub_count else "")
        msg = (f"Supprimer le groupe « {tag_name} » ?{sub_msg}\n"
               f"{n} évènement(s) / période(s) seront déplacés vers Non-classés.")
        if not messagebox.askyesno("Supprimer le groupe", msg, parent=self):
            return
        for ev in self._events:
            if ev.group_name in affected_groups:
                ev.group_name = "Non-classés"
        for p in self._periods:
            if p.group_name in affected_groups:
                p.group_name = "Non-classés"
        for g in affected_groups:
            self._tags.pop(g, None)
        self._apply_group_colors()
        self._refresh()

    def _set_bulk_tag_visibility(self, mode: str):
        """mode: 'all' | 'none' | 'invert'. Locked tags are skipped."""
        for tag in self._tags.values():
            if tag.locked_visible:
                continue
            if   mode == "all":    tag.visible = True
            elif mode == "none":   tag.visible = False
            elif mode == "invert": tag.visible = not tag.visible
        self._refresh_visibility_only()

    def _refresh_visibility_only(self):
        """Lightweight refresh used when only group visibility changed.

        Skips the (slow) per-item list rebuild when the right-pane filter is
        « all », and avoids re-deriving every event color (no item changed).
        Autosave is also debounced.
        """
        visible_tags = self._visible_tag_names()
        ve = [ev for ev in self._events if ev.group_name in visible_tags]
        vp = [p  for p  in self._periods if p.group_name  in visible_tags]
        self._timeline.set_events(ve)
        self._timeline.set_periods(vp)
        self._tag_panel.refresh_tags(self._tags, self._events, self._periods)
        # Keep the right-pane filter combo in sync with the live group list.
        self._list_panel.set_group_choices(
            self._tag_names_for_ui(),
            descendants_map=self._build_descendants_map())
        # If the user is filtering on "Groupes visibles", a visibility change
        # actually changes which items are listed → rebuild the right pane.
        if self._list_filter_mode == "Groupes visibles":
            self._list_panel.refresh_list(self._events, self._periods,
                                            visible_tags)
        self._schedule_autosave()

    def _build_descendants_map(self) -> dict:
        """Map each group name to the set of itself + all its descendants."""
        return {
            name: {name, *self._tag_descendants(name)}
            for name in self._tags
        }

    def _set_list_filter_mode(self, mode: str):
        """
        New API: `mode` is either "Tout" (show everything) or a specific
        group name. Re-runs `_refresh` so the list and timeline align.
        """
        self._list_filter_mode = mode or "Tout"
        self._refresh()

    def _visible_tag_names(self) -> set[str]:
        """Effective visibility: a tag is visible only if it AND every
        ancestor in its tree path are visible (or locked)."""
        return {n for n in self._tags if self._tag_is_effectively_visible(n)}

    def _show_drag_indicator(self, label: str, x_root: int, y_root: int,
                             target_tag: Optional[str] = None,
                             copy: bool = False):
        self._hide_drag_indicator()
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        try:
            win.attributes("-topmost", True)
        except tk.TclError:
            pass
        verb = "Copier" if copy else "Déplacer"
        text = f"{verb} : {label}"
        if target_tag:
            text += f"  →  {target_tag}"
        tag = tk.Label(
            win, text=text,
            bg=PALETTE["panel2"], fg=PALETTE["text"],
            relief="solid", bd=1, padx=10, pady=6,
            font=("Segoe UI", 9, "bold"))
        tag.pack()
        win.geometry(f"+{x_root + 18}+{y_root + 18}")
        self._drag_window = win
        self._drag_label = tag

    def _move_drag_indicator(self, x_root: int, y_root: int,
                             target_tag: Optional[str] = None,
                             copy: bool = False):
        if not self._drag_payload or not self._drag_window or not self._drag_label:
            return
        verb = "Copier" if copy else "Déplacer"
        text = f"{verb} : {self._drag_payload['label']}"
        if target_tag:
            text += f"  →  {target_tag}"
        self._drag_label.configure(text=text)
        self._drag_window.geometry(f"+{x_root + 18}+{y_root + 18}")

    def _hide_drag_indicator(self):
        if self._drag_window is not None:
            self._drag_window.destroy()
        self._drag_window = None
        self._drag_label = None

    @staticmethod
    def _ctrl_pressed(event) -> bool:
        # Tk event.state bit 0x4 = Control modifier (on Windows, Linux, macOS).
        try:
            return bool(event.state & 0x4)
        except (AttributeError, TypeError):
            return False

    def _unique_event_name(self, base: str) -> str:
        existing = {ev.name for ev in self._events}
        if base not in existing:
            return base
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

    def _unique_period_name(self, base: str) -> str:
        existing = {p.name for p in self._periods}
        if base not in existing:
            return base
        i = 2
        while f"{base} {i}" in existing:
            i += 1
        return f"{base} {i}"

    def _begin_item_drag(self, kind: str, idx: int, label: str, event):
        self._drag_payload = {"kind": kind, "idx": idx, "label": label}
        target_tag = self._tag_panel.tag_at_root(event.x_root, event.y_root)
        self._tag_panel.set_drop_target(target_tag)
        self._show_drag_indicator(label, event.x_root, event.y_root,
                                   target_tag, self._ctrl_pressed(event))

    def _on_global_drag_motion(self, event):
        if not self._drag_payload:
            return
        target_tag = self._tag_panel.tag_at_root(event.x_root, event.y_root)
        self._tag_panel.set_drop_target(target_tag)
        self._move_drag_indicator(event.x_root, event.y_root,
                                   target_tag, self._ctrl_pressed(event))

    def _on_global_drag_release(self, event):
        if not self._drag_payload:
            return
        target_tag = self._tag_panel.tag_at_root(event.x_root, event.y_root)
        copy_mode = self._ctrl_pressed(event)
        payload = self._drag_payload
        self._drag_payload = None
        self._tag_panel.set_drop_target(None)
        self._hide_drag_indicator()
        if not target_tag:
            return

        target = self._ensure_tag_exists(target_tag)

        if payload["kind"] == "event":
            if not (0 <= payload["idx"] < len(self._events)):
                return
            item = self._events[payload["idx"]]
            if copy_mode:
                new_ev = CosmicEvent(
                    name=self._unique_event_name(item.name + " (copie)"),
                    years_ago=item.years_ago,
                    color=item.color,
                    description=item.description,
                    group_name=target,
                    absolute_date=item.absolute_date)
                self._events.append(new_ev)
            else:
                item.group_name = target
        else:
            if not (0 <= payload["idx"] < len(self._periods)):
                return
            item = self._periods[payload["idx"]]
            if copy_mode:
                new_per = CosmicPeriod(
                    name=self._unique_period_name(item.name + " (copie)"),
                    years_ago_start=item.years_ago_start,
                    years_ago_end=item.years_ago_end,
                    color=item.color,
                    description=item.description,
                    group_name=target,
                    absolute_date_start=item.absolute_date_start,
                    absolute_date_end=item.absolute_date_end,
                    is_ongoing=item.is_ongoing)
                self._periods.append(new_per)
            else:
                item.group_name = target
        self._apply_group_colors()
        self._refresh()

    def _add_event(self, name: str, years_ago: float, color: str,
                    description: str = "", group_name=None):
        ref = self._get_ref_years()
        tgt = self._get_tgt_secs()
        if not ref or not tgt: return
        if years_ago > ref:
            messagebox.showwarning(
                "Hors période",
                f"'{name}' ({years_ago:,.0f} ans) est antérieur à la période "
                f"de référence ({ref:,.0f} ans).\nIl sera placé au début.")
        display_years_ago = min(years_ago, ref)
        fraction  = (ref - display_years_ago) / ref
        pos       = fraction_to_position(fraction, tgt)
        result    = format_result(
            pos, tgt,
            realtime_ref_years=self._get_realtime_ref_years(),
            realtime_years_ago=display_years_ago)
        gname = self._normalize_group_name(group_name)
        # Color is derived from the group's base color; the `color` arg is ignored.
        base = self._tags[gname].color
        ev = CosmicEvent(name=name, years_ago=years_ago,
                          color=color_variant_for(base, name),
                          description=description,
                          group_name=gname,
                          absolute_date=years_ago_to_iso(years_ago),
                          fraction=fraction, result_str=result)
        self._events.append(ev)
        self._last_result_var.set(
            f"{name} :  {result.replace(chr(10), '  ·  ')}")
        self._refresh()

    def _remove_event(self, idx: int):
        if 0 <= idx < len(self._events):
            self._events.pop(idx)
            self._refresh()

    def _edit_event(self, idx: int):
        if not (0 <= idx < len(self._events)):
            return
        ev = self._events[idx]
        def save(payload):
            ev.name          = payload["name"]
            ev.description   = payload["description"]
            ev.years_ago     = payload["years_ago"]
            if payload.get("absolute_date"):
                ev.absolute_date = payload["absolute_date"]
            else:
                ev.absolute_date = years_ago_to_iso(payload["years_ago"])
            ev.group_name = self._normalize_group_name(payload.get("group_name"))
            self._recalculate_all()
        EditDialog(self, "event", ev, save, tags=self._tag_names_for_ui())

    def _add_period(self, name: str, ys: float, ye: float, color: str,
                     description: str = "", group_name=None,
                     is_ongoing: bool = False):
        ref = self._get_ref_years()
        tgt = self._get_tgt_secs()
        if not ref or not tgt: return
        if ys > ref:
            messagebox.showwarning(
                "Hors période",
                f"'{name}' (début il y a {ys:,.0f} ans) est antérieur à la "
                f"période de référence ({ref:,.0f} ans).\n"
                f"Le début sera placé au commencement.")
        gname = self._normalize_group_name(group_name)
        base = self._tags[gname].color
        per = CosmicPeriod(name=name, years_ago_start=ys,
                            years_ago_end=(0.0 if is_ongoing else ye),
                            color=color_variant_for(base, name),
                            description=description,
                            group_name=gname,
                            absolute_date_start=years_ago_to_iso(ys),
                            absolute_date_end=(None if is_ongoing
                                                else years_ago_to_iso(ye)),
                            is_ongoing=is_ongoing)
        self._compute_period(per, ref, tgt)
        self._periods.append(per)
        self._refresh()

    def _remove_period(self, idx: int):
        if 0 <= idx < len(self._periods):
            self._periods.pop(idx)
            self._refresh()

    def _edit_period(self, idx: int):
        if not (0 <= idx < len(self._periods)):
            return
        per = self._periods[idx]
        def save(payload):
            per.name                = payload["name"]
            per.description         = payload["description"]
            per.is_ongoing          = bool(payload.get("is_ongoing", False))
            per.years_ago_start     = payload["years_ago_start"]
            if per.is_ongoing:
                per.years_ago_end       = 0.0
                per.absolute_date_end   = None
            else:
                per.years_ago_end       = payload["years_ago_end"]
                per.absolute_date_end   = (payload.get("absolute_date_end")
                                            or years_ago_to_iso(payload["years_ago_end"]))
            per.absolute_date_start = (payload.get("absolute_date_start")
                                        or years_ago_to_iso(payload["years_ago_start"]))
            per.group_name = self._normalize_group_name(payload.get("group_name"))
            self._recalculate_all()
        EditDialog(self, "period", per, save, tags=self._tag_names_for_ui())

    def _compute_period(self, per: CosmicPeriod, ref: float, tgt: float):
        realtime_ref_years = self._get_realtime_ref_years()
        visible_start = min(per.years_ago_start, ref)
        # Ongoing periods always end at "now" — do NOT use the stored end.
        if per.is_ongoing:
            visible_end = 0.0
        else:
            visible_end = min(per.years_ago_end, ref)
        per.fraction_start = (ref - visible_start) / ref
        per.fraction_end   = (ref - visible_end)   / ref
        per.start_str      = format_result(
            fraction_to_position(per.fraction_start, tgt), tgt,
            realtime_ref_years=realtime_ref_years,
            realtime_years_ago=visible_start)
        if per.is_ongoing:
            per.end_str = "en cours"
        else:
            per.end_str = format_result(
                fraction_to_position(per.fraction_end,   tgt), tgt,
                realtime_ref_years=realtime_ref_years,
                realtime_years_ago=visible_end)
        duration_target_sec = max(0.0, per.fraction_end - per.fraction_start) * tgt
        per.duration_str    = format_duration_seconds(duration_target_sec)

    def _clear_events(self):
        self._events.clear()
        self._periods.clear()
        self._refresh()

    def _recalculate_all(self):
        ref = self._get_ref_years()
        tgt = self._get_tgt_secs()
        realtime_ref_years = self._get_realtime_ref_years()
        if not ref or not tgt: return
        for ev in self._events:
            ya = min(ev.years_ago, ref)
            ev.fraction   = (ref - ya) / ref
            pos           = fraction_to_position(ev.fraction, tgt)
            ev.result_str = format_result(
                pos, tgt,
                realtime_ref_years=realtime_ref_years,
                realtime_years_ago=ya)
        for per in self._periods:
            self._compute_period(per, ref, tgt)
        self._timeline.set_target(tgt, realtime_ref_years=realtime_ref_years)
        self._refresh()

    def _refresh(self):
        # Re-derive every item's display color from its group's base color.
        self._apply_group_colors()
        visible_tags = self._visible_tag_names()
        visible_events = [
            ev for ev in self._events
            if ev.group_name in visible_tags
        ]
        visible_periods = [
            per for per in self._periods
            if per.group_name in visible_tags
        ]
        self._timeline.set_events(visible_events)
        self._timeline.set_periods(visible_periods)

        # The panel always receives the FULL lists; it filters internally
        # by the chosen group (or "Tout" = no group filter). Master-list
        # indices stay intact so context-menu actions target the correct item.
        self._list_panel.set_group_choices(
            self._tag_names_for_ui(),
            descendants_map=self._build_descendants_map())
        self._list_panel.refresh_list(self._events, self._periods,
                                        visible_tags)

        self._tag_panel.refresh_tags(self._tags, self._events, self._periods)
        self._input_panel.refresh_tag_choices()
        self._autosave()

    # ── Focus on timeline (called by double-click in the list) ────────────────

    def _focus_event(self, idx: int):
        if 0 <= idx < len(self._events):
            self._timeline.focus_on_event(self._events[idx].fraction)

    def _focus_period(self, idx: int):
        if 0 <= idx < len(self._periods):
            p = self._periods[idx]
            self._timeline.focus_on_period(p.fraction_start, p.fraction_end)

    # ── Persistence ────────────────────────────────────────────────────────────

    def _serialize(self) -> dict:
        return {
            "version":               4,
            "ref_period":            self._ref_combo.get(),
            "ref_custom_years":      self._ref_custom.get(),
            "target_scale":          self._tgt_combo.get(),
            "target_custom_seconds": self._tgt_custom.get(),
            "tags": [
                {"name":           tag.name,
                 "color":          tag.color,
                 "visible":        tag.visible,
                 "locked_visible": tag.locked_visible,
                 "parent_name":    tag.parent_name}
                for tag in self._tags.values()
            ],
            "events": [
                {"name": ev.name, "years_ago": ev.years_ago,
                 "absolute_date": ev.absolute_date,
                 "description": ev.description,
                 "group_name": ev.group_name}
                for ev in self._events
            ],
            "periods": [
                {"name":                p.name,
                 "years_ago_start":     p.years_ago_start,
                 "years_ago_end":       p.years_ago_end,
                 "absolute_date_start": p.absolute_date_start,
                 "absolute_date_end":   p.absolute_date_end,
                 "is_ongoing":          p.is_ongoing,
                 "description":         p.description,
                 "group_name":          p.group_name}
                for p in self._periods
            ],
        }

    def _apply_serialized(self, data: dict, merge: bool = False):
        """
        Apply data from a JSON payload.

        - merge=False (default): replace the current state (used by autoload).
        - merge=True: ref/target settings are kept; tags are added if missing;
          events and periods are upserted by `name` (existing entries with the
          same name are updated, new ones are appended).
        """
        if not merge:
            ref = data.get("ref_period")
            if ref in REFERENCE_PERIODS:
                self._ref_combo.set(ref)
                if REFERENCE_PERIODS[ref] is None:
                    self._ref_custom.delete(0, "end")
                    self._ref_custom.insert(0, str(data.get("ref_custom_years", "")))
                    self._ref_custom.pack(side="left", padx=(0, 6),
                                           after=self._ref_combo)
                else:
                    self._ref_custom.pack_forget()

            tgt = data.get("target_scale")
            if tgt in TARGET_SCALES:
                self._tgt_combo.set(tgt)
                if TARGET_SCALES[tgt] is None:
                    self._tgt_custom.delete(0, "end")
                    self._tgt_custom.insert(0, str(data.get("target_custom_seconds", "")))
                    self._tgt_custom.pack(side="left", padx=(0, 6),
                                           after=self._tgt_combo)
                else:
                    self._tgt_custom.pack_forget()

        # ── Tags / Groups ────────────────────────────────────────────────────
        if not merge:
            self._tags.clear()
        for raw in data.get("tags", data.get("groups", [])):
            try:
                name = str(raw["name"]).strip()
                if not name:
                    continue
                if merge and name in self._tags:
                    continue
                parent = raw.get("parent_name")
                self._tags[name] = CosmicTag(
                    name=name,
                    color=str(raw.get("color", self._next_group_color())),
                    visible=bool(raw.get("visible", True)),
                    locked_visible=bool(raw.get("locked_visible", False)),
                    parent_name=(str(parent) if parent else None))
            except (KeyError, TypeError, ValueError):
                continue
        self._ensure_default_tag()

        # ── Events ───────────────────────────────────────────────────────────
        if not merge:
            self._events.clear()
        events_by_name = {ev.name: i for i, ev in enumerate(self._events)}
        for raw in data.get("events", []):
            try:
                # Group selection — fall back to legacy tag_names list if needed.
                gname = raw.get("group_name")
                if not gname:
                    legacy = raw.get("tag_names") or raw.get("group_names") or []
                    gname = next((t for t in legacy if t and t != "Non-classés"),
                                  legacy[0] if legacy else "Non-classés")
                gname = self._normalize_group_name(gname)

                abs_date = raw.get("absolute_date")
                stored_ya = float(raw["years_ago"])
                ya = stored_ya
                if abs_date:
                    rebuilt = iso_to_years_ago(str(abs_date))
                    if rebuilt is not None:
                        ya = rebuilt
                else:
                    derived = years_ago_to_iso(stored_ya)
                    if derived is not None:
                        abs_date = derived
                new_ev = CosmicEvent(
                    name=str(raw["name"]),
                    years_ago=ya,
                    color=str(raw.get("color", EVENT_COLORS[0])),
                    description=str(raw.get("description", "")),
                    group_name=gname,
                    absolute_date=str(abs_date) if abs_date else None)
            except (KeyError, TypeError, ValueError):
                continue
            if merge and new_ev.name in events_by_name:
                self._events[events_by_name[new_ev.name]] = new_ev
            else:
                events_by_name[new_ev.name] = len(self._events)
                self._events.append(new_ev)

        # ── Periods ──────────────────────────────────────────────────────────
        if not merge:
            self._periods.clear()
        periods_by_name = {p.name: i for i, p in enumerate(self._periods)}
        for raw in data.get("periods", []):
            try:
                gname = raw.get("group_name")
                if not gname:
                    legacy = raw.get("tag_names") or raw.get("group_names") or []
                    gname = next((t for t in legacy if t and t != "Non-classés"),
                                  legacy[0] if legacy else "Non-classés")
                gname = self._normalize_group_name(gname)

                abs_start = raw.get("absolute_date_start")
                abs_end   = raw.get("absolute_date_end")
                ys = float(raw["years_ago_start"])
                ye = float(raw["years_ago_end"])
                if abs_start:
                    rebuilt = iso_to_years_ago(str(abs_start))
                    if rebuilt is not None: ys = rebuilt
                else:
                    derived = years_ago_to_iso(ys)
                    if derived is not None: abs_start = derived
                if abs_end:
                    rebuilt = iso_to_years_ago(str(abs_end))
                    if rebuilt is not None: ye = rebuilt
                else:
                    derived = years_ago_to_iso(ye)
                    if derived is not None: abs_end = derived
                is_ongoing = bool(raw.get("is_ongoing", False))
                if is_ongoing:
                    ye, abs_end = 0.0, None
                new_per = CosmicPeriod(
                    name=str(raw["name"]),
                    years_ago_start=ys,
                    years_ago_end=ye,
                    color=str(raw.get("color", EVENT_COLORS[0])),
                    description=str(raw.get("description", "")),
                    group_name=gname,
                    absolute_date_start=str(abs_start) if abs_start else None,
                    absolute_date_end=str(abs_end) if abs_end else None,
                    is_ongoing=is_ongoing)
            except (KeyError, TypeError, ValueError):
                continue
            if merge and new_per.name in periods_by_name:
                self._periods[periods_by_name[new_per.name]] = new_per
            else:
                periods_by_name[new_per.name] = len(self._periods)
                self._periods.append(new_per)

        # Rename the legacy "general" tag from older saves.
        self._migrate_legacy_general_tag()
        self._recalculate_all()

    def _autosave(self):
        """Trigger an autosave; debounced so rapid changes coalesce."""
        self._schedule_autosave()

    def _schedule_autosave(self, delay_ms: int = 300):
        """Coalesce many rapid mutations into a single disk write."""
        if getattr(self, "_autosave_after_id", None):
            try: self.after_cancel(self._autosave_after_id)
            except tk.TclError: pass
        self._autosave_after_id = self.after(delay_ms, self._autosave_now)

    def _autosave_now(self):
        self._autosave_after_id = None
        try:
            AUTOSAVE_PATH.write_text(
                json.dumps(self._serialize(), ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            pass

    def _autoload(self):
        if not AUTOSAVE_PATH.exists():
            return
        try:
            data = json.loads(AUTOSAVE_PATH.read_text(encoding="utf-8"))
            self._apply_serialized(data)
        except (OSError, json.JSONDecodeError):
            pass

    def _import_file(self):
        path = filedialog.askopenfilename(
            title="Charger des évènements",
            filetypes=FILE_TYPES,
            initialdir=str(AUTOSAVE_PATH.parent))
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            self._apply_serialized(data, merge=True)
        except (OSError, json.JSONDecodeError, KeyError) as e:
            messagebox.showerror("Chargement impossible", f"Fichier invalide :\n{e}")

    def _export_file(self):
        path = filedialog.asksaveasfilename(
            title="Exporter les évènements",
            defaultextension=".events",
            filetypes=FILE_TYPES,
            initialfile="cosmic_events.events",
            initialdir=str(AUTOSAVE_PATH.parent))
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self._serialize(), ensure_ascii=False, indent=2),
                encoding="utf-8")
            messagebox.showinfo("Export réussi",
                                 f"{len(self._events)} évènement(s) exportés vers :\n{path}")
        except OSError as e:
            messagebox.showerror("Export impossible", str(e))

    def _export_group(self, group_name: str):
        """Export every event/period belonging to a single group."""
        if group_name not in self._tags:
            return
        events  = [ev for ev in self._events  if ev.group_name == group_name]
        periods = [p  for p  in self._periods if p.group_name  == group_name]
        if not events and not periods:
            messagebox.showinfo(
                "Groupe vide",
                f"Le groupe « {group_name} » ne contient ni évènement ni période.")
            return
        # Build a self-contained payload — include this tag and any
        # ancestors needed for the hierarchy to make sense on import.
        tag_chain = self._tag_ancestors(group_name)
        tag_defs = []
        for n in tag_chain:
            t = self._tags[n]
            tag_defs.append({
                "name": t.name, "color": t.color,
                "visible": t.visible, "locked_visible": t.locked_visible,
                "parent_name": t.parent_name,
            })
        payload = {
            "version": 4,
            "tags": tag_defs,
            "events": [
                {"name": ev.name, "years_ago": ev.years_ago,
                 "absolute_date": ev.absolute_date,
                 "description": ev.description,
                 "group_name": ev.group_name}
                for ev in events
            ],
            "periods": [
                {"name": p.name,
                 "years_ago_start": p.years_ago_start,
                 "years_ago_end":   p.years_ago_end,
                 "absolute_date_start": p.absolute_date_start,
                 "absolute_date_end":   p.absolute_date_end,
                 "is_ongoing": p.is_ongoing,
                 "description": p.description,
                 "group_name":  p.group_name}
                for p in periods
            ],
        }
        # Filename safe-ish from the group name.
        safe = "".join(c for c in group_name
                       if c.isalnum() or c in (" ", "-", "_")).strip() \
               or "groupe"
        path = filedialog.asksaveasfilename(
            title=f"Exporter le groupe « {group_name} »",
            defaultextension=".events",
            filetypes=FILE_TYPES,
            initialfile=f"{safe}.events",
            initialdir=str(AUTOSAVE_PATH.parent))
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8")
            messagebox.showinfo(
                "Export réussi",
                f"« {group_name} » : {len(events)} évènement(s), "
                f"{len(periods)} période(s) → {path}")
        except OSError as e:
            messagebox.showerror("Export impossible", str(e))



def main():
    app = CosmicScaleApp()
    app._autoload()
    app.mainloop()

"""Interactive Desktop Application for DressMe Shopper Agent  (modern UI).

Provides a clean two-pane GUI to:
1. Browse and select a garment image file.
2. Enter prompt, price, budget, category, and occasion.
3. Handle dynamic Step 4 clarification popups if facts (like budget) are missing.
4. Display the decision, Qwen/Fallback badge, compatible outfits count, and score breakdown.

Design
------
Palette : #1c1c1c (ink)  #6b8a3a (moss)  #faf9f6 (paper)  + neutral tints derived from them
Font    : Rustand Soft Medium  (commercial font -> must be installed on the machine,
          or dropped as .otf/.ttf files into a ./fonts folder next to this script;
          on Windows they are then loaded automatically, no install needed).
          Falls back to Segoe UI / Helvetica if the font is not found.
"""

import sys
import threading
import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

from schemas import CandidateItem, EvaluatePurchaseRequest, DecisionType, SessionStatus
from agent import PurchaseAgent


# ----------------------------------------------------------------------------
# Theme
# ----------------------------------------------------------------------------
INK = "#1c1c1c"            # brand dark
MOSS = "#6b8a3a"           # brand accent
PAPER = "#faf9f6"          # brand light

# Tints derived from the three brand colors
INK_RAISED = "#262626"
INK_INPUT = "#2f2f2f"
INK_LINE = "#3d3d3d"
INK_MUTED = "#9b9a94"
MOSS_HOVER = "#7a9b44"
MOSS_PRESS = "#5a7530"
MOSS_DEEP = "#4d6628"
PAPER_CARD = "#f2f0ea"
PAPER_LINE = "#e0ddd3"
PAPER_MUTED = "#74726a"

# Semantic decision colors (kept muted so they sit well with the palette)
C_BUY = MOSS
C_CONSIDER = "#b8892b"
C_SKIP = "#b0483a"

FONT_CANDIDATES = ("Rustand Soft Medium", "Rustand Soft", "Rustand")
FONT_FALLBACKS = ("Segoe UI", "Helvetica Neue", "Helvetica", "Arial")


def _register_local_fonts():
    """Load any font files in ./fonts for this process only (Windows)."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        FR_PRIVATE = 0x10
        fonts_dir = Path(__file__).resolve().parent / "fonts"
        if fonts_dir.is_dir():
            for p in list(fonts_dir.glob("*.otf")) + list(fonts_dir.glob("*.ttf")):
                ctypes.windll.gdi32.AddFontResourceExW(str(p), FR_PRIVATE, 0)
    except Exception:
        pass


def _enable_hidpi():
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


def _pick_font_family(root: tk.Tk) -> str:
    families = set(tkfont.families(root))
    for name in FONT_CANDIDATES + FONT_FALLBACKS:
        if name in families:
            return name
    return "TkDefaultFont"


# ----------------------------------------------------------------------------
# Custom widgets
# ----------------------------------------------------------------------------
def _round_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(pts, smooth=True, **kw)


class RoundButton(tk.Canvas):
    """Flat rounded button with hover / press / disabled states."""

    def __init__(self, parent, text, command, *, parent_bg, fill, hover, press=None,
                 fg=PAPER, outline=None, font=None, padx=20, pady=11, radius=10,
                 disabled_fill=None, disabled_fg=None):
        f = tkfont.Font(font=font)
        width = f.measure(text) + padx * 2
        height = f.metrics("linespace") + pady * 2
        super().__init__(parent, width=width, height=height, bg=parent_bg,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._text, self._command, self._font = text, command, font
        self._fill, self._hover, self._press = fill, hover, press or hover
        self._fg, self._outline, self._radius = fg, outline, radius
        self._disabled_fill = disabled_fill or fill
        self._disabled_fg = disabled_fg or fg
        self._enabled = True
        self._state = "normal"

        self.bind("<Configure>", lambda e: self._draw())
        self.bind("<Enter>", lambda e: self._set_visual("hover"))
        self.bind("<Leave>", lambda e: self._set_visual("normal"))
        self.bind("<ButtonPress-1>", lambda e: self._set_visual("press"))
        self.bind("<ButtonRelease-1>", self._on_release)

    def _set_visual(self, state):
        self._state = state
        self._draw()

    def _on_release(self, event):
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        self._set_visual("hover" if inside else "normal")
        if self._enabled and inside and self._command:
            self._command()

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._state = "normal"
        self._draw()

    def set_text(self, text):
        self._text = text
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        if not self._enabled:
            fill, fg = self._disabled_fill, self._disabled_fg
        else:
            fill = {"normal": self._fill, "hover": self._hover, "press": self._press}[self._state]
            fg = self._fg
        _round_rect(self, 1, 1, w - 1, h - 1, self._radius, fill=fill,
                    outline=self._outline if (self._outline and self._enabled) else (
                        self._outline or ""), width=1)
        self.create_text(w / 2, h / 2, text=self._text, fill=fg, font=self._font)


class Pill(tk.Canvas):
    """Small rounded label (decision / engine badge)."""

    def __init__(self, parent, *, parent_bg, font, padx=16, pady=6):
        self._font = font
        self._padx, self._pady = padx, pady
        self._f = tkfont.Font(font=font)
        super().__init__(parent, bg=parent_bg, highlightthickness=0, bd=0,
                         height=self._f.metrics("linespace") + pady * 2, width=10)
        self._text, self._fill, self._fg, self._outline = "", PAPER_CARD, INK, None

    def set(self, text, fill, fg=PAPER, outline=None):
        self._text, self._fill, self._fg, self._outline = text, fill, fg, outline
        w = self._f.measure(text) + self._padx * 2 if text else 1
        self.configure(width=w)
        self._draw()

    def _draw(self):
        self.delete("all")
        if not self._text:
            return
        w = int(self.cget("width"))
        h = int(self.cget("height"))
        _round_rect(self, 1, 1, w - 1, h - 1, h // 2, fill=self._fill,
                    outline=self._outline or "", width=1)
        self.create_text(w / 2, h / 2, text=self._text, fill=self._fg, font=self._font)


class ScoreBar(tk.Canvas):
    def __init__(self, parent, *, bg, track=PAPER_LINE, fill=MOSS, height=8):
        super().__init__(parent, height=height, bg=bg, highlightthickness=0, bd=0)
        self._track, self._fill, self._value = track, fill, 0.0
        self.bind("<Configure>", lambda e: self._draw())

    def set(self, value, color=None):
        self._value = max(0.0, min(100.0, value or 0.0))
        if color:
            self._fill = color
        self._draw()

    def _draw(self):
        self.delete("all")
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4:
            return
        r = h // 2
        _round_rect(self, 0, 0, w, h, r, fill=self._track, outline="")
        fw = max(h, int(w * self._value / 100.0)) if self._value > 0 else 0
        if fw:
            _round_rect(self, 0, 0, fw, h, r, fill=self._fill, outline="")


class AskDialog(tk.Toplevel):
    """Themed modal prompt (replacement for simpledialog.askstring)."""

    def __init__(self, parent, title, message, prompt, family):
        super().__init__(parent, bg=INK)
        self.title(title)
        self.resizable(False, False)
        self.transient(parent)
        self.result = None

        body = tk.Frame(self, bg=INK, padx=28, pady=24)
        body.pack(fill=tk.BOTH, expand=True)

        tk.Label(body, text=title, bg=INK, fg=PAPER, font=(family, 15),
                 anchor="w").pack(fill=tk.X)
        tk.Frame(body, bg=MOSS, height=2, width=36).pack(anchor="w", pady=(8, 14))
        tk.Label(body, text=message, bg=INK, fg=INK_MUTED, font=(family, 10),
                 wraplength=380, justify=tk.LEFT, anchor="w").pack(fill=tk.X)
        tk.Label(body, text=prompt.upper(), bg=INK, fg=INK_MUTED, font=(family, 8),
                 anchor="w").pack(fill=tk.X, pady=(16, 4))

        self.var = tk.StringVar()
        self.entry = tk.Entry(body, textvariable=self.var, bg=INK_INPUT, fg=PAPER,
                              insertbackground=PAPER, relief=tk.FLAT, bd=0,
                              highlightthickness=1, highlightbackground=INK_LINE,
                              highlightcolor=MOSS, font=(family, 11))
        self.entry.pack(fill=tk.X, ipady=8)

        row = tk.Frame(body, bg=INK)
        row.pack(fill=tk.X, pady=(20, 0))
        RoundButton(row, "Continue", self._ok, parent_bg=INK, fill=MOSS, hover=MOSS_HOVER,
                    press=MOSS_PRESS, fg=PAPER, font=(family, 10)).pack(side=tk.RIGHT)
        RoundButton(row, "Cancel", self._cancel, parent_bg=INK, fill=INK, hover=INK_RAISED,
                    fg=INK_MUTED, outline=INK_LINE, font=(family, 10)).pack(side=tk.RIGHT, padx=(0, 10))

        self.bind("<Return>", lambda e: self._ok())
        self.bind("<Escape>", lambda e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.update_idletasks()
        x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        self.grab_set()
        self.entry.focus_set()

    def _ok(self):
        self.result = self.var.get()
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


# ----------------------------------------------------------------------------
# Main application
# ----------------------------------------------------------------------------
class ShopperAgentApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("DressMe — Shopper Agent")
        self.root.geometry("1220x800")
        self.root.minsize(1060, 720)
        self.root.configure(bg=INK)

        self.family = _pick_font_family(root)

        # Initialize Agent
        self.agent = PurchaseAgent()

        # State Variables
        self.last_rec = None
        self.image_path_var = tk.StringVar(value="")
        default_sample = Path(__file__).resolve().parent / "data" / "sample_camel_blazer.jpg"
        if default_sample.exists():
            self.image_path_var.set(str(default_sample))

        self.query_var = tk.StringVar(value="Should I buy this?")
        self.category_var = tk.StringVar(value="blazer")
        self.price_var = tk.StringVar(value="149.99")
        self.budget_var = tk.StringVar(value="")  # Leave empty to test dynamic Step 4 clarification!
        self.occasion_var = tk.StringVar(value="work")
        self.color_var = tk.StringVar(value="auto-detect")
        self.style_var = tk.StringVar(value="formal")

        self._setup_styles()
        self._build_ui()
        self._show_empty_state()

    # ------------------------------------------------------------------ styles
    def f(self, size, *mods):
        return (self.family, size, *mods)

    def _setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")

        style.configure(
            "Ink.TCombobox",
            fieldbackground=INK_INPUT, background=INK_INPUT, foreground=PAPER,
            arrowcolor=INK_MUTED, bordercolor=INK_LINE, lightcolor=INK_INPUT,
            darkcolor=INK_INPUT, selectbackground=INK_INPUT, selectforeground=PAPER,
            padding=7, relief="flat",
        )
        style.map(
            "Ink.TCombobox",
            fieldbackground=[("readonly", INK_INPUT), ("focus", INK_INPUT)],
            bordercolor=[("focus", MOSS)],
            lightcolor=[("focus", MOSS)],
            darkcolor=[("focus", MOSS)],
            arrowcolor=[("pressed", MOSS), ("active", PAPER)],
            selectbackground=[("focus", INK_INPUT)],
            selectforeground=[("focus", PAPER)],
        )
        self.root.option_add("*TCombobox*Listbox.background", INK_RAISED)
        self.root.option_add("*TCombobox*Listbox.foreground", PAPER)
        self.root.option_add("*TCombobox*Listbox.selectBackground", MOSS)
        self.root.option_add("*TCombobox*Listbox.selectForeground", PAPER)
        self.root.option_add("*TCombobox*Listbox.font", self.f(10))
        self.root.option_add("*TCombobox*Listbox.borderWidth", 0)

        style.layout("Paper.Vertical.TScrollbar", [
            ("Vertical.Scrollbar.trough", {
                "sticky": "ns",
                "children": [("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})],
            })
        ])
        style.configure("Paper.Vertical.TScrollbar", troughcolor=PAPER_CARD,
                        background=PAPER_LINE, bordercolor=PAPER_CARD,
                        lightcolor=PAPER_LINE, darkcolor=PAPER_LINE, width=8)
        style.map("Paper.Vertical.TScrollbar", background=[("active", MOSS)])

    # ---------------------------------------------------------------- layout
    def _build_ui(self):
        self.root.columnconfigure(0, weight=0, minsize=410)
        self.root.columnconfigure(1, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._build_left_panel()
        self._build_right_panel()

    # --- Left (inputs) -------------------------------------------------------
    def _build_left_panel(self):
        left = tk.Frame(self.root, bg=INK, padx=30, pady=28)
        left.grid(row=0, column=0, sticky="nsew")

        # Brand
        brand = tk.Frame(left, bg=INK)
        brand.pack(fill=tk.X)
        tk.Label(brand, text="DressMe", bg=INK, fg=PAPER, font=self.f(26)).pack(side=tk.LEFT)
        dot = tk.Canvas(brand, width=12, height=12, bg=INK, highlightthickness=0)
        dot.create_oval(1, 1, 11, 11, fill=MOSS, outline="")
        dot.pack(side=tk.LEFT, padx=(6, 0), pady=(14, 0))
        tk.Label(left, text="SHOPPER AGENT", bg=INK, fg=MOSS, font=self.f(9),
                 anchor="w").pack(fill=tk.X, pady=(0, 4))
        tk.Label(left,
                 text="Grounded purchase evaluation — five tools, deterministic scoring and Qwen reasoning.",
                 bg=INK, fg=INK_MUTED, font=self.f(9), wraplength=340, justify=tk.LEFT,
                 anchor="w").pack(fill=tk.X, pady=(0, 20))

        # Image
        self._field_label(left, "Garment image").pack(fill=tk.X, pady=(0, 5))
        img_row = tk.Frame(left, bg=INK)
        img_row.pack(fill=tk.X, pady=(0, 14))
        self.img_entry = self._entry(img_row, self.image_path_var)
        self.img_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 8))
        RoundButton(img_row, "Browse", self._browse_image, parent_bg=INK, fill=INK,
                    hover=INK_RAISED, press=INK_INPUT, fg=PAPER, outline=INK_LINE,
                    font=self.f(10), padx=16, pady=8).pack(side=tk.RIGHT)

        # Prompt
        self._field_label(left, "Your question").pack(fill=tk.X, pady=(0, 5))
        self._entry(left, self.query_var).pack(fill=tk.X, ipady=8, pady=(0, 14))

        # Grid of attributes
        grid = tk.Frame(left, bg=INK)
        grid.pack(fill=tk.X)
        grid.columnconfigure(0, weight=1, uniform="col")
        grid.columnconfigure(1, weight=1, uniform="col")

        cats = ["jacket", "blazer", "shirt", "t-shirt", "skirt", "shorts", "shoes", "sandals",
                "sneakers", "coat", "raincoat", "sweater", "hoodie", "cardigan", "dress",
                "trousers", "jeans"]
        colors = ["auto-detect", "black", "white", "navy", "grey", "cream", "beige", "brown",
                  "camel", "blue", "green", "pink", "burgundy", "red"]
        styles = ["formal", "smart_casual", "casual", "business", "evening"]

        self._grid_field(grid, 0, 0, "Category", self._combo(grid, self.category_var, cats))
        self._grid_field(grid, 0, 1, "Color", self._combo(grid, self.color_var, colors))
        self._grid_field(grid, 2, 0, "Style", self._combo(grid, self.style_var, styles))
        self._grid_field(grid, 2, 1, "Occasion", self._entry(grid, self.occasion_var), entry=True)
        self._grid_field(grid, 4, 0, "Item price ($)", self._entry(grid, self.price_var), entry=True)
        self._grid_field(grid, 4, 1, "Your budget ($)", self._entry(grid, self.budget_var), entry=True)

        tk.Label(left,
                 text="Tip — leave budget blank to see Qwen detect the missing fact and ask you.",
                 bg=INK, fg=INK_MUTED, font=self.f(8), wraplength=340, justify=tk.LEFT,
                 anchor="w").pack(fill=tk.X, pady=(2, 18))

        # Actions
        self.eval_button = RoundButton(
            left, "Evaluate with Qwen", self._start_evaluation, parent_bg=INK,
            fill=MOSS, hover=MOSS_HOVER, press=MOSS_PRESS, fg=PAPER, font=self.f(11),
            pady=13, radius=12, disabled_fill=MOSS_DEEP, disabled_fg=INK_MUTED)
        self.eval_button.pack(fill=tk.X, pady=(0, 10))

        sec = tk.Frame(left, bg=INK)
        sec.pack(fill=tk.X)
        sec.columnconfigure(0, weight=1, uniform="b")
        sec.columnconfigure(1, weight=1, uniform="b")
        self.fallback_btn = RoundButton(
            sec, "Rule-based fallback", self._on_fallback_clicked, parent_bg=INK, fill=INK,
            hover=INK_RAISED, press=INK_INPUT, fg=PAPER, outline=INK_LINE, font=self.f(10),
            pady=10, radius=12)
        self.fallback_btn.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.qwen_btn = RoundButton(
            sec, "Shopper advice", self._on_qwen_clicked, parent_bg=INK, fill=INK,
            hover=INK_RAISED, press=INK_INPUT, fg=PAPER, outline=INK_LINE, font=self.f(10),
            pady=10, radius=12, disabled_fg=INK_LINE)
        self.qwen_btn.grid(row=0, column=1, sticky="ew", padx=(5, 0))
        self.qwen_btn.set_enabled(False)

        # Status (bottom)
        status_wrap = tk.Frame(left, bg=INK)
        status_wrap.pack(side=tk.BOTTOM, fill=tk.X)
        tk.Frame(status_wrap, bg=INK_LINE, height=1).pack(fill=tk.X, pady=(0, 10))
        self.status_var = tk.StringVar(value="Ready.")
        tk.Label(status_wrap, textvariable=self.status_var, bg=INK, fg=INK_MUTED,
                 font=self.f(9), wraplength=340, justify=tk.LEFT, anchor="w").pack(fill=tk.X)

    # --- Right (results) -----------------------------------------------------
    def _build_right_panel(self):
        right = tk.Frame(self.root, bg=PAPER, padx=36, pady=28)
        right.grid(row=0, column=1, sticky="nsew")

        top = tk.Frame(right, bg=PAPER)
        top.pack(fill=tk.X)
        tk.Label(top, text="EVALUATION", bg=PAPER, fg=PAPER_MUTED, font=self.f(9)).pack(side=tk.LEFT)
        self.engine_badge = Pill(top, parent_bg=PAPER, font=self.f(9), padx=14, pady=5)
        self.engine_badge.pack(side=tk.RIGHT)

        # Verdict banner
        banner = tk.Frame(right, bg=PAPER)
        banner.pack(fill=tk.X, pady=(14, 6))

        self.decision_pill = Pill(banner, parent_bg=PAPER, font=self.f(14), padx=22, pady=9)
        self.decision_pill.pack(side=tk.LEFT)

        score_box = tk.Frame(banner, bg=PAPER)
        score_box.pack(side=tk.RIGHT)
        self.score_label = tk.Label(score_box, text="--", bg=PAPER, fg=INK, font=self.f(32))
        self.score_label.pack(side=tk.LEFT)
        tk.Label(score_box, text="/100", bg=PAPER, fg=PAPER_MUTED, font=self.f(12)
                 ).pack(side=tk.LEFT, padx=(4, 0), pady=(14, 0))

        # 5-Star Rating display directly next to the score
        stars_wrap = tk.Frame(score_box, bg=PAPER)
        stars_wrap.pack(side=tk.LEFT, padx=(14, 0), pady=(8, 0))
        self.stars_yellow = tk.Label(stars_wrap, text="", bg=PAPER, fg="#EAB308", font=self.f(18))
        self.stars_yellow.pack(side=tk.LEFT)
        self.stars_grey = tk.Label(stars_wrap, text="☆☆☆☆☆", bg=PAPER, fg="#9CA3AF", font=self.f(18))
        self.stars_grey.pack(side=tk.LEFT)
        self.stars_text = tk.Label(stars_wrap, text="", bg=PAPER, fg=PAPER_MUTED, font=self.f(11))
        self.stars_text.pack(side=tk.LEFT, padx=(4, 0))

        self.score_bar = ScoreBar(right, bg=PAPER)
        self.score_bar.pack(fill=tk.X, pady=(6, 18))

        # Results card
        card = tk.Frame(right, bg=PAPER_CARD, highlightthickness=1, highlightbackground=PAPER_LINE)
        card.pack(fill=tk.BOTH, expand=True)

        self.results_text = tk.Text(
            card, wrap=tk.WORD, font=self.f(10), bg=PAPER_CARD, fg=INK,
            relief=tk.FLAT, bd=0, highlightthickness=0, padx=26, pady=20,
            spacing1=2, spacing3=4, cursor="arrow", selectbackground=MOSS,
            selectforeground=PAPER, insertwidth=0, tabs=(300, "right", 400, "right"),
        )
        scrollbar = ttk.Scrollbar(card, orient=tk.VERTICAL, command=self.results_text.yview,
                                  style="Paper.Vertical.TScrollbar")
        self.results_text.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, padx=(0, 3), pady=3)
        self.results_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        t = self.results_text
        t.tag_configure("h", font=self.f(9), foreground=MOSS_DEEP, spacing1=18, spacing3=6)
        t.tag_configure("title", font=self.f(13), foreground=INK, spacing3=2)
        t.tag_configure("body", font=self.f(11), foreground=INK, spacing1=2, spacing3=6,
                        lmargin1=0, lmargin2=0)
        t.tag_configure("key", font=self.f(10), foreground=PAPER_MUTED)
        t.tag_configure("val", font=self.f(10), foreground=INK)
        t.tag_configure("bullet", font=self.f(10), foreground=INK, lmargin1=14, lmargin2=28,
                        spacing3=3)
        t.tag_configure("muted", font=self.f(10), foreground=PAPER_MUTED)
        t.tag_configure("warn", font=self.f(10), foreground=C_SKIP)
        t.tag_configure("accent", font=self.f(10), foreground=MOSS_DEEP)
        t.tag_configure("rule", font=self.f(2), spacing3=0)
        t.tag_configure("star_yellow", font=self.f(13), foreground="#EAB308")
        t.tag_configure("star_grey", font=self.f(13), foreground="#9CA3AF")

    # ---------------------------------------------------------- widget helpers
    def _field_label(self, parent, text):
        return tk.Label(parent, text=text.upper(), bg=INK, fg=INK_MUTED, font=self.f(8), anchor="w")

    def _entry(self, parent, var):
        return tk.Entry(parent, textvariable=var, bg=INK_INPUT, fg=PAPER,
                        insertbackground=PAPER, relief=tk.FLAT, bd=0,
                        highlightthickness=1, highlightbackground=INK_LINE,
                        highlightcolor=MOSS, font=self.f(10),
                        selectbackground=MOSS, selectforeground=PAPER)

    def _combo(self, parent, var, values):
        return ttk.Combobox(parent, textvariable=var, values=values, style="Ink.TCombobox",
                            font=self.f(10))

    def _grid_field(self, grid, row, col, label, widget, entry=False):
        padx = (0, 7) if col == 0 else (7, 0)
        self._field_label(grid, label).grid(row=row, column=col, sticky="ew", padx=padx, pady=(0, 5))
        if entry:
            widget.grid(row=row + 1, column=col, sticky="ew", padx=padx, pady=(0, 14), ipady=8)
        else:
            widget.grid(row=row + 1, column=col, sticky="ew", padx=padx, pady=(0, 14))

    # ------------------------------------------------------------ text helpers
    def _t_clear(self):
        self.results_text.configure(state=tk.NORMAL)
        self.results_text.delete("1.0", tk.END)

    def _t_done(self):
        self.results_text.configure(state=tk.DISABLED)
        self.results_text.yview_moveto(0)

    def _t(self, text, *tags):
        self.results_text.insert(tk.END, text, tags)

    def _t_heading(self, text):
        self._t(text.upper() + "\n", "h")

    def _t_kv(self, key, value):
        self._t(f"{key}\t", "key")
        self._t(f"{value}\n", "val")

    def _show_empty_state(self):
        self._t_clear()
        self._t("Nothing evaluated yet\n", "title")
        self._t("Pick a garment image, set the details on the left and press ", "muted")
        self._t("Evaluate with Qwen", "accent")
        self._t(". The verdict, score, outfit matches and grounded evidence will appear here.\n", "muted")
        self._t_done()
        self.decision_pill.set("NO VERDICT", PAPER_CARD, fg=PAPER_MUTED, outline=PAPER_LINE)
        self.score_label.config(text="--")
        self.stars_yellow.config(text="")
        self.stars_grey.config(text="☆☆☆☆☆")
        self.stars_text.config(text="")
        self.score_bar.set(0)

    # ---------------------------------------------------------------- actions
    def _browse_image(self):
        file_path = filedialog.askopenfilename(
            title="Select Garment Image",
            filetypes=[("Image Files", "*.jpg *.jpeg *.png *.webp *.bmp"), ("All Files", "*.*")]
        )
        if file_path:
            self.image_path_var.set(file_path)

    def _build_candidate_and_request(self):
        price = None
        if self.price_var.get().strip():
            try:
                price = float(self.price_var.get().strip())
            except ValueError:
                price = None

        budget = None
        if self.budget_var.get().strip():
            try:
                budget = float(self.budget_var.get().strip())
            except ValueError:
                budget = None

        color_val = self.color_var.get().strip().lower()
        if color_val == "auto-detect":
            color_val = "unknown"

        cat_val = self.category_var.get().strip().lower()
        style_val = [self.style_var.get().strip().lower()] if self.style_var.get().strip() else ["formal"]

        candidate = CandidateItem(
            name=f"{self.category_var.get().title()}",
            category=cat_val,
            color=color_val,
            style=style_val,
            price=price,
            budget=budget,
            image_path=self.image_path_var.get().strip() or None,
            target_occasion=self.occasion_var.get().strip().lower()
        )

        request = EvaluatePurchaseRequest(
            candidate=candidate,
            user_query=self.query_var.get().strip(),
            budget=budget
        )
        return candidate, request

    def _start_evaluation(self):
        self.eval_button.set_enabled(False)
        self.qwen_btn.set_enabled(False)
        self.status_var.set("Consulting wardrobe and waiting for Qwen in Ollama (up to 120s)…")
        self._t_clear()
        self._t("Working on it\n", "title")
        self._t("Analyzing your wardrobe, calculating deterministic metrics and waiting for "
                "Qwen's reasoning…\n", "muted")
        self._t_done()
        self.decision_pill.set("THINKING…", PAPER_CARD, fg=PAPER_MUTED, outline=PAPER_LINE)
        self.engine_badge.set("", PAPER)
        self.root.update_idletasks()

        threading.Thread(target=self._run_pipeline, daemon=True).start()

    def _run_pipeline(self):
        try:
            _, request = self._build_candidate_and_request()

            # Turn 1: Run through Agent
            rec = self.agent.evaluate(request)

            # Check if Step 4 paused for clarification
            if rec.status == SessionStatus.AWAITING_INPUT:
                self.root.after(0, lambda: self._handle_clarification_popup(rec))
                return

            self.last_rec = rec
            # Completed immediately - display Qwen by default
            self.root.after(0, lambda: self._display_results(rec, view_mode="qwen"))

        except Exception as e:
            err_str = str(e)
            self.root.after(0, lambda msg=err_str: self._handle_error(msg))

    def _on_fallback_clicked(self):
        """Prints the deterministic Fallback rule-based explanation when the user clicks this button."""
        if self.last_rec is not None:
            # Display fallback from the existing evaluation
            self._display_results(self.last_rec, view_mode="fallback")
            self.status_var.set("Displayed deterministic fallback explanation.")
        else:
            # Fast deterministic fallback evaluation without waiting for LLM
            self.status_var.set("Running fast deterministic fallback evaluation…")
            try:
                _, request = self._build_candidate_and_request()
                rec = self.agent.evaluate(request, skip_llm=True)
                if rec.status == SessionStatus.AWAITING_INPUT:
                    self._handle_clarification_popup(rec)
                    return
                self.last_rec = rec
                self._display_results(rec, view_mode="fallback")
                self.status_var.set("Deterministic fallback complete.")
            except Exception as e:
                err_str = str(e)
                self._handle_error(err_str)

    def _on_qwen_clicked(self):
        """Switches display back to personal shopper's recommendation."""
        if self.last_rec is not None and self.last_rec.qwen_summary:
            self._display_results(self.last_rec, view_mode="qwen")
            self.status_var.set("Displayed your personal shopper's recommendation.")
        else:
            messagebox.showinfo(
                "Personal Shopper",
                "Personal shopper advice is not available for this session. Please click 'Evaluate with Qwen'."
            )

    def _handle_clarification_popup(self, rec):
        self.status_var.set("Agent requested more information…")
        dlg = AskDialog(
            self.root,
            "Information needed",
            f"The agent needs more information to evaluate affordability:\n\n{rec.clarification_question}",
            "Enter your budget ($)",
            self.family,
        )
        self.root.wait_window(dlg)
        user_input = dlg.result

        if user_input is None:
            # User cancelled
            self.status_var.set("Evaluation cancelled.")
            self.eval_button.set_enabled(True)
            self.decision_pill.set("CANCELLED", PAPER_CARD, fg=PAPER_MUTED, outline=PAPER_LINE)
            return

        # Update budget field for visibility
        self.budget_var.set(user_input.strip())
        self.status_var.set("Resuming evaluation from checkpoint…")

        # Run Step 5 resumption in background thread
        threading.Thread(
            target=lambda: self._resume_evaluation(rec.session_id, user_input.strip()),
            daemon=True
        ).start()

    def _resume_evaluation(self, session_id: str, user_response: str):
        try:
            resume_req = EvaluatePurchaseRequest(
                session_id=session_id,
                user_response=user_response
            )
            final_rec = self.agent.evaluate(resume_req)
            self.last_rec = final_rec
            self.root.after(0, lambda: self._display_results(final_rec, view_mode="qwen"))
        except Exception as e:
            err_str = str(e)
            self.root.after(0, lambda msg=err_str: self._handle_error(msg))

    # ---------------------------------------------------------------- display
    def _display_results(self, rec, view_mode="qwen"):
        self.eval_button.set_enabled(True)
        self.fallback_btn.set_enabled(True)
        self.qwen_btn.set_enabled(bool(rec.qwen_summary))

        # Decision banner
        dec = rec.decision.value if rec.decision else "UNKNOWN"
        color = {"BUY": C_BUY, "CONSIDER": C_CONSIDER}.get(dec, C_SKIP)
        self.decision_pill.set(dec, color)

        if rec.overall_score is not None:
            score_text = f"{rec.overall_score:.2f}/100"
            self.score_label.config(text=f"{rec.overall_score:.1f}")
            self.score_bar.set(rec.overall_score, color)
            num_yellow = max(0, min(5, int(round(rec.overall_score / 20.0))))
            num_grey = 5 - num_yellow
            self.stars_yellow.config(text="★" * num_yellow)
            self.stars_grey.config(text="☆" * num_grey)
            self.stars_text.config(text=f"({num_yellow}/5)")
        else:
            score_text = ""
            self.score_label.config(text="--")
            self.stars_yellow.config(text="")
            self.stars_grey.config(text="☆☆☆☆☆")
            self.stars_text.config(text="")
            self.score_bar.set(0)

        # Sync color_var if auto-detect was used
        if rec.detected_color and self.color_var.get() in ["auto-detect", "unknown", ""]:
            self.color_var.set(rec.detected_color)

        self._t_clear()

        # ---- Engine section
        if view_mode == "fallback":
            self.engine_badge.set("FALLBACK · RULE-BASED", PAPER_CARD, fg=C_CONSIDER, outline=C_CONSIDER)
            self.status_var.set("Displaying deterministic fallback explanation.")
            self._t("Rule-based recommendation\n", "title")
            self._t(f"{rec.fallback_summary or rec.summary}\n", "body")
        elif rec.qwen_summary:
            self.engine_badge.set("", PAPER)
            self.status_var.set("Evaluation complete. Use “Rule-based fallback” for the deterministic output.")
            self._t("your personal shopper's recommendation\n", "title")
            self._t(f"{rec.qwen_summary}\n", "body")
        else:
            self.engine_badge.set("", PAPER)
            self.status_var.set("Personal shopper was unable to respond. Use “Rule-based fallback”.")
            self._t("No shopper response\n", "title")
            self._t("The personal shopper was unable to answer within the time limit.\n", "warn")
            self._t("Press ", "muted")
            self._t("Rule-based fallback", "accent")
            self._t(" on the left to see the deterministic output.\n", "muted")

        self._t(f"Session {rec.session_id}\n", "muted")

        if rec.overall_score is not None:
            num_yellow = max(0, min(5, int(round(rec.overall_score / 20.0))))
            num_grey = 5 - num_yellow
            self._t("Rating: ", "key")
            self._t("★" * num_yellow, "star_yellow")
            self._t("☆" * num_grey, "star_grey")
            self._t(f"  ({num_yellow}/5 stars)\n", "muted")

        # ---- Garment specs (user prompt omitted from evaluated garment)
        det_color = getattr(rec, "detected_color", None) or self.color_var.get()
        det_cat = getattr(rec, "detected_category", None) or self.category_var.get()
        det_style = getattr(rec, "detected_style", None) or self.style_var.get()
        det_occ = getattr(rec, "detected_occasion", None) or self.occasion_var.get()

        self._t_heading("Evaluated garment")
        self._t_kv("Category", det_cat)
        self._t_kv("Color (vision / metadata)", det_color)
        self._t_kv("Style", det_style)
        self._t_kv("Occasion", det_occ)

        # ---- Outfits
        self._t_heading("Outfit compatibility")
        count = rec.compatible_outfits_count or len(rec.outfit_examples)
        self._t(f"Compatible with {count} outfit(s) in your wardrobe.\n", "body")
        for outfit in rec.outfit_examples:
            self._t(f"•  [{outfit.occasion.upper()}] ", "bullet", "accent")
            self._t(f"{outfit.description}  ", "bullet")
            self._t(f"{outfit.compatibility_score:.2f}%\n", "bullet", "muted")

        # ---- Wardrobe redundancy & color comparison (Delta E omitted)
        if rec.similar_items:
            self._t_heading("Wardrobe redundancy & color comparison")
            for m in rec.similar_items[:3]:
                col_text = ""
                if m.color_similarity is not None:
                    col_text = f" | Color match: {m.color_similarity*100:.1f}%"
                self._t(f"•  '{m.garment.name}' ({m.garment.color} {m.garment.category})\n", "bullet", "accent")
                self._t(f"    Garment similarity: {m.similarity_score*100:.1f}%{col_text}\n", "bullet", "muted")
                if m.redundancy_warning:
                    self._t(f"    {m.redundancy_warning}\n", "bullet", "warn")

        # ---- Evidence
        self._t_heading("Grounded evidence")
        for ev in rec.evidence:
            self._t(f"•  {ev}\n", "bullet")

        # ---- Score breakdown
        if rec.score_breakdown:
            b = rec.score_breakdown
            self._t_heading("Deterministic score breakdown")
            rows = [
                ("Outfit compatibility", f"{b.outfit_compatibility:.2f}%", f"+{b.outfit_contribution:.2f}"),
                ("Wardrobe gap score", f"{b.gap_contribution_score:.2f}%", f"+{b.gap_contribution:.2f}"),
                ("Versatility", f"{b.versatility_score:.2f}%", f"+{b.versatility_contribution:.2f}"),
                ("Personal style match", f"{b.style_match_score:.2f}%", f"+{b.style_contribution:.2f}"),
                ("Low redundancy", f"{100 - b.redundancy_raw_score:.2f}%", f"+{b.low_redundancy_contribution:.2f}"),
            ]
            for label, pct, contrib in rows:
                self._t(f"{label}\t", "key")
                self._t(f"{pct}\t", "val")
                self._t(f"{contrib}\n", "accent")
            if b.budget_penalty > 0:
                self._t("Budget overage penalty\t", "key")
                self._t("\t", "val")
                self._t(f"-{b.budget_penalty:.2f}\n", "warn")

        self._t_done()

    def _handle_error(self, err_msg):
        self.eval_button.set_enabled(True)
        self.status_var.set("Error during evaluation.")
        self.decision_pill.set("ERROR", C_SKIP)
        messagebox.showerror("Evaluation Error", f"An error occurred:\n{err_msg}")


def launch_gui():
    _enable_hidpi()
    _register_local_fonts()
    root = tk.Tk()
    ShopperAgentApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch_gui()
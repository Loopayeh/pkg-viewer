#!/usr/bin/env python3
"""PKG Viewer - PS4 + PS5 (FIH/CNT). Clean dark UI (tkinter) + CLI --info mode."""
import io
import json
import os
import struct
import sys

APP_VERSION = "v1.14.1"  # bump on every release — the updater compares this
UPDATE_REPO = "Loopayeh/pkg-viewer"
SUPPORT_ADDR = "0x839a30D52Ef7D2b53e818b9931efd7FE6F472e50"  # USDT (BEP-20)
SUPPORT_URL = ("https://link.trustwallet.com/send?coin=20000714&address="
               "0x839a30D52Ef7D2b53e818b9931efd7FE6F472e50"
               "&token_id=0x55d398326f99059fF775485246999027B3197955")


def _settings_path():
    """User settings file. Never raises."""
    try:
        if sys.platform.startswith("win"):
            base = os.environ.get("APPDATA") or os.path.expanduser("~")
            d = os.path.join(base, "PKGViewer")
        else:
            d = os.path.join(os.path.expanduser("~"), ".config", "pkgviewer")
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, "settings.json")
    except Exception:
        return None


def _load_settings():
    try:
        p = _settings_path()
        if p and os.path.isfile(p):
            with open(p, "r", encoding="utf-8-sig") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _save_settings(patch):
    try:
        p = _settings_path()
        if not p:
            return
        d = _load_settings()
        d.update(patch or {})
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f)
    except Exception:
        pass

# ---------------- rounded buttons (PIL face on a real tk.Button) ----------------
try:
    import tkinter as _tk
    from tkinter import font as _tkfont
    _TK_OK = True
except ImportError:
    _tk = None
    _tkfont = None
    _TK_OK = False
try:
    from PIL import Image as _PILImage, ImageDraw as _PILDraw, ImageTk as _PILImageTk
    _PIL_OK = True
except ImportError:
    _PILImage = _PILDraw = _PILImageTk = None
    _PIL_OK = False

_RBTN_RADIUS = 4
_RBTN_PAD = {"accent": (16, 9), "ghost": (12, 7)}
_RBTN_FACE = {
    "accent": {"face": "#4f8ef7", "hover": "#6fa8ff", "pressed": "#3b70c9",
               "fg": "#171717", "disabled_face": "#2a2a2a", "disabled_fg": "#8b93a5"},
    "ghost": {"face": "#404040", "hover": "#2c3342", "pressed": "#333a44",
              "fg": "#f1f3f8", "disabled_face": "#2a2a2a", "disabled_fg": "#8b93a5"},
}
_RBTN_DEFAULT_BG = "#171717"
_RBTN_DEFAULT_FONT = ("Segoe UI", 10)


def _rbtn_kind_of(style):
    if style and "Ghost" in style:
        return "ghost"
    return "accent"


def _rbtn_face_image(w, h, radius, color):
    s = 3
    img = _PILImage.new("RGBA", (w * s, h * s), (0, 0, 0, 0))
    _PILDraw.Draw(img).rounded_rectangle([0, 0, w * s - 1, h * s - 1],
                                         radius=radius * s, fill=color)
    return img.resize((w, h), _PILImage.LANCZOS)


class RoundedButton(_tk.Button):
    """tk.Button with a rounded-rectangle face rendered by PIL.

    Drop-in for the ttk.Button call sites in run_gui: same text /
    textvariable / command options, same pack/grid/place API, plus
    .config(text=...), .config(style=...) and .config(state=...).
    See mkbtn for the PIL-missing fallback.
    """

    def __init__(self, parent, text="", textvariable=None, style="Accent.TButton",
                 kind=None, command=None, bg=_RBTN_DEFAULT_BG,
                 font=_RBTN_DEFAULT_FONT, radius=_RBTN_RADIUS,
                 cursor="hand2", **kw):
        self._kind = kind or _rbtn_kind_of(style)
        self._text = text
        self._var = textvariable
        self._radius = radius
        self._font = _tkfont.Font(font=font)
        self._padx, self._pady = _RBTN_PAD[self._kind]
        self._pal = _RBTN_FACE[self._kind]
        self._imgs = {}
        self._pil = {}
        self._pressed = False
        self._hovered = False
        super().__init__(parent, text=text, textvariable=textvariable,
                         font=font, fg=self._pal["fg"],
                         activeforeground=self._pal["fg"],
                         disabledforeground=self._pal["disabled_fg"],
                         bg=bg, activebackground=bg,
                         borderwidth=0, relief="flat", highlightthickness=0,
                         overrelief="flat", padx=0, pady=0, cursor=cursor,
                         compound="center", command=command, **kw)
        self._refresh()
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self.bind("<ButtonPress-1>", lambda _e: self._set_pressed(True))
        self.bind("<ButtonRelease-1>", lambda _e: self._set_pressed(False))
        self._watch_var()

    # -- internals --
    def _watch_var(self):
        if self._var is not None:
            try:
                self._var.trace_add("write", lambda *_a: self._refresh())
            except Exception:
                pass

    def _label(self):
        try:
            if self._var is not None:
                return self._var.get()
        except Exception:
            pass
        return self._text

    def _refresh(self):
        label = self._label()
        tw = self._font.measure(label) if label else 0
        lh = self._font.metrics("linespace")
        w = max(tw + 2 * self._padx, 2 * self._radius + 12)
        h = lh + 2 * self._pady
        pal = self._pal
        self._pil = {k: _rbtn_face_image(w, h, self._radius, pal[c])
                     for k, c in (("normal", "face"), ("hover", "hover"),
                                   ("pressed", "pressed"),
                                   ("disabled", "disabled_face"))}
        self._imgs = {k: _PILImageTk.PhotoImage(im)
                      for k, im in self._pil.items()}
        try:
            super().configure(width=w, height=h)
        except Exception:
            pass
        self._show(self._current_face())

    def _current_face(self):
        try:
            st = super().cget("state")
        except Exception:
            st = "normal"
        if st == "disabled":
            return "disabled"
        if self._pressed:
            return "pressed"
        if self._hovered:
            return "hover"
        return "normal"

    def _show(self, which):
        try:
            super().configure(image=self._imgs[which])
        except Exception:
            pass

    def _set_hover(self, on):
        self._hovered = on
        self._show(self._current_face())

    def _set_pressed(self, on):
        self._pressed = on
        self._show(self._current_face())

    # -- ttk-compatible option API --
    def configure(self, cnf=None, **kw):
        if cnf is None and not kw:
            return super().configure()
        if isinstance(cnf, dict):
            kw = dict(cnf, **kw)
            cnf = None
        if isinstance(cnf, str) and not kw:
            if cnf == "text":
                return self._text
            return super().configure(cnf)
        opts = dict(kw)
        dirty = False
        if "style" in opts:
            kind = _rbtn_kind_of(opts.pop("style"))
            if kind != self._kind:
                self._kind = kind
                self._padx, self._pady = _RBTN_PAD[kind]
                self._pal = _RBTN_FACE[kind]
                try:
                    super().configure(fg=self._pal["fg"],
                                      activeforeground=self._pal["fg"])
                except Exception:
                    pass
                dirty = True
        if "kind" in opts:
            kind = opts.pop("kind")
            if kind in _RBTN_FACE and kind != self._kind:
                self._kind = kind
                self._padx, self._pady = _RBTN_PAD[kind]
                self._pal = _RBTN_FACE[kind]
                dirty = True
        if "textvariable" in opts:
            self._var = opts.pop("textvariable")
            opts["textvariable"] = self._var
            self._watch_var()
            dirty = True
        if "text" in opts:
            self._text = opts.pop("text")
            opts["text"] = self._text
            dirty = True
        if "bg" in opts or "background" in opts:
            opts["activebackground"] = opts.get("bg", opts.get("background"))
        if opts:
            try:
                super().configure(**opts)
            except Exception:
                pass
        if dirty or "state" in opts:
            self._refresh()
        return None

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        return super().cget(key)

    def __setitem__(self, key, value):
        self.configure(**{key: value})

    def __getitem__(self, key):
        return self.cget(key)


def mkbtn(parent, text="", textvariable=None, style="Accent.TButton",
          command=None, bg=_RBTN_DEFAULT_BG, font=_RBTN_DEFAULT_FONT, **kw):
    """Make a rounded button; falls back to ttk.Button without PIL."""
    if _TK_OK and _PIL_OK:
        return RoundedButton(parent, text=text, textvariable=textvariable,
                             style=style, command=command, bg=bg, font=font,
                             **kw)
    from tkinter import ttk as _ttk
    return _ttk.Button(parent, text=text, textvariable=textvariable,
                       style=style, command=command, **kw)


class PillLabel(_tk.Label):
    """tk.Label with a rounded-pill face rendered by PIL (for badges).

    Same palette, just rounded. Supports .config(text=...), .config(bg=...)
    (face color) and textvariable; parent_bg paints the corners.
    Falls back to a plain label only via mkpill(has_pil=False) path.
    """

    def __init__(self, parent, text="", textvariable=None, bg="#2a2a2a",
                 fg="#171717", font=_RBTN_DEFAULT_FONT, padx=8, pady=3,
                 radius=8, parent_bg="#202020", **kw):
        self._text = text
        self._var = textvariable
        self._face = bg
        self._parent_bg = parent_bg
        self._font = _tkfont.Font(font=font)
        self._padx, self._pady = padx, pady
        self._radius = radius
        self._img = None
        self._pil = None
        super().__init__(parent, text=text, textvariable=textvariable,
                         font=font, fg=fg, bg=parent_bg,
                         borderwidth=0, highlightthickness=0,
                         padx=0, pady=0, **kw)
        self._refresh()
        if self._var is not None:
            try:
                self._var.trace_add("write", lambda *_a: self._refresh())
            except Exception:
                pass

    def _label(self):
        try:
            if self._var is not None:
                return self._var.get()
        except Exception:
            pass
        return self._text

    def _refresh(self):
        label = self._label()
        tw = self._font.measure(label) if label else 0
        lh = self._font.metrics("linespace")
        w = max(tw + 2 * self._padx, 2 * self._radius + 10)
        h = lh + 2 * self._pady
        self._pil = _rbtn_face_image(w, h, self._radius, self._face)
        self._img = _PILImageTk.PhotoImage(self._pil)
        try:
            super().configure(image=self._img, compound="center",
                              width=w, height=h)
        except Exception:
            pass

    def configure(self, cnf=None, **kw):
        if cnf is None and not kw:
            return super().configure()
        if isinstance(cnf, dict):
            kw = dict(cnf, **kw)
            cnf = None
        if isinstance(cnf, str) and not kw:
            if cnf == "text":
                return self._text
            return super().configure(cnf)
        opts = dict(kw)
        dirty = False
        if "text" in opts:
            self._text = opts.pop("text")
            opts["text"] = self._text
            dirty = True
        if "textvariable" in opts:
            self._var = opts.pop("textvariable")
            opts["textvariable"] = self._var
            if self._var is not None:
                try:
                    self._var.trace_add("write",
                                        lambda *_a: self._refresh())
                except Exception:
                    pass
            dirty = True
        if "bg" in opts or "background" in opts:
            self._face = opts.pop("bg", opts.pop("background", self._face))
            dirty = True
        if "fg" in opts or "foreground" in opts:
            pass
        if opts:
            try:
                super().configure(**opts)
            except Exception:
                pass
        if dirty:
            self._refresh()
        return None

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key in ("bg", "background"):
            return self._face
        return super().cget(key)


def mkpill(parent, text="", textvariable=None, bg="#2a2a2a", fg="#171717",
           font=_RBTN_DEFAULT_FONT, parent_bg="#202020", **kw):
    """Make a rounded pill badge; falls back to tk.Label without PIL."""
    if _TK_OK and _PIL_OK:
        return PillLabel(parent, text=text, textvariable=textvariable, bg=bg,
                         fg=fg, font=font, parent_bg=parent_bg, **kw)
    return _tk.Label(parent, text=text, textvariable=textvariable, bg=bg,
                     fg=fg, font=font, padx=8, pady=3, **kw)

CNT_MAGIC = b"\x7fCNT"
FIH_MAGIC = b"\x7fFIH"
PS3_MAGIC = b"\x7fPKG"

# PS3 NPDRM (from PyKG / ps3 pkg tools: fixed key, CTR with riv; debug = SHA1-XOR)
PS3_KEY = bytes.fromhex("2e7b71d7c9c9a14ea3221f188828b8f8")
PS3_HDR_FMT = ">4sHHIIIIQQQ48s16s16s"
PS3_ITEM_FMT = ">IIQQII"
PS3_DIR_FLAG = 0x04
try:
    from cryptography.hazmat.primitives.ciphers import Cipher as _Cipher
    from cryptography.hazmat.primitives.ciphers import algorithms as _Algos
    from cryptography.hazmat.primitives.ciphers import modes as _Modes
    HAS_PS3_AES = True
except ImportError:
    HAS_PS3_AES = False

# ---------------- parsing (verified on samples) ----------------

def u32be(b, o):
    return struct.unpack_from(">I", b, o)[0]


def u64be(b, o):
    return struct.unpack_from(">Q", b, o)[0]


def u64le(b, o):
    return struct.unpack_from("<Q", b, o)[0]


def parse_cnt_entries(f, base, entry_count, entry_table_off):
    f.seek(base + entry_table_off)
    raw = f.read(entry_count * 32)
    ents = []
    for i in range(entry_count):
        e = raw[i * 32:(i + 1) * 32]
        if len(e) < 32:
            break
        v = struct.unpack(">8I", e)
        ents.append({"id": v[0], "name_off": v[1], "f1": v[2], "f2": v[3],
                     "off": v[4], "size": v[5]})
    return ents


def read_name_table(f, base, ents):
    nt_entry = next((e for e in ents if e["id"] == 512), None)
    if not nt_entry:
        return b""
    f.seek(base + nt_entry["off"])
    return f.read(nt_entry["size"])


def entry_name(nt, off):
    end = nt.find(b"\x00", off)
    if end < 0:
        return ""
    return nt[off:end].decode("ascii", errors="replace")


def parse_sfo(data):
    out = {}
    try:
        if data[:4] != b"\x00PSF":
            return {"_error": "bad magic %r" % data[:4]}
        ver, key_off, data_off, count = struct.unpack_from("<4I", data, 4)
        for i in range(count):
            eo = 20 + i * 16
            key_rel, fmt, dlen, dmax, doff = struct.unpack_from("<HHIII", data, eo)
            ks = key_off + key_rel
            ke = data.find(b"\x00", ks)
            key = data[ks:ke].decode("utf-8", errors="replace")
            val_off = data_off + doff
            if fmt == 0x0204:
                ve = data.find(b"\x00", val_off, val_off + dmax)
                if ve < 0:
                    ve = val_off + dlen
                out[key] = data[val_off:ve].decode("utf-8", errors="replace")
            elif fmt == 0x0404:
                out[key] = struct.unpack_from("<I", data, val_off)[0]
            else:
                out[key] = data[val_off:val_off + dlen].hex(" ")
        return out
    except Exception as e:
        return {"_error": str(e)}


REGION_NAMES = {"EP": "Europe", "UP": "Americas", "JP": "Japan", "HP": "Asia"}
PS4_CAT_TYPES = {"gd": "Base Game", "ac": "DLC", "gp": "Update"}


def content_region(cid):
    """Region from content-ID prefix (EP0002-... -> Europe)."""
    try:
        pre = (cid or "").split("-")[0][:2].upper()
        return REGION_NAMES.get(pre, pre or "-")
    except Exception:
        return "-"


def fmt_fw(v):
    """Decode PS5 fw hex (0x0250...) -> '2.50'. Passes other values through."""
    if v is None or v == "":
        return "-"
    try:
        n = v if isinstance(v, int) else int(str(v).strip(), 0)
        top = (n >> 48) & 0xFFFF
        if not top:
            return str(v)
        return f"{(top >> 8) & 0xFF:X}.{top & 0xFF:02X}"
    except Exception:
        return str(v)


def ps4_pkg_type(cat):
    if not cat:
        return "-"
    lab = PS4_CAT_TYPES.get(str(cat).lower())
    return lab if lab else str(cat)


def cnt_package_type(hdr):
    """FPKG vs retail for PS4 CNT: bit 31 of pkg_type @0x04 (big-endian).

    Per psdevwiki/UnPKG: FILE_TYPE_FLAGS_RETAIL = 1 << 31. Retail PKGs
    have pkg_type like 0x83000001/0x81000001; fpkg builds (even DUPLEX,
    which carry non-zero digest bytes at 0x100..0x200) have it clear
    (e.g. 0x00000001/0x40000001). The 0x100..0x200 area holds SHA256
    digests, NOT an RSA signature, so zero-testing it is wrong.
    """
    try:
        if len(hdr) >= 8:
            ptype = struct.unpack_from(">I", hdr, 0x04)[0]
            if ptype & 0x80000000:
                return "OFC (Official)"
            return "FPKG (Fake)"
    except Exception:
        pass
    return "-"


def lman_summary(meta_kind, rd):
    """Bottom-bar summary à la LMAN: Type (Fake) (REGION) - vVER - System SYS."""
    try:
        typ = str(rd.get("Type", "") or "")
        pkg = str(rd.get("Package", "") or rd.get("Signature", ""))
        if not typ:
            # encrypted stubs / table-less kinds have no Type row: use
            # the Package label base (e.g. "OFC (Official)" -> "OFC").
            typ = pkg
        base = typ.split("(")[0].strip() or typ or "-"
        fake = ""
        if "fake" in pkg.lower() or "fpkg" in pkg.lower():
            fake = " (Fake)"
        elif "official" in pkg.lower() or pkg.lower().startswith("ofc"):
            fake = " (Official)"
        region = str(rd.get("Region", "") or "")
        short = REGION_SHORT.get(region, region[:2].upper() if region else "-")
        ver = (rd.get("Version", "") or rd.get("Content Ver", "") or "-")
        ver = str(ver).strip() or "-"
        if ver != "-" and not ver.lower().startswith("v"):
            ver = "v" + ver
        sysv = str(rd.get("Min. System", "") or "").strip()
        out = f"{base}{fake} ({short}) - {ver}"
        if sysv and sysv != "-":
            out += f" - System {sysv}"
        return out
    except Exception:
        return ""


def _param_json_meta(meta):
    lp = meta.get("localizedParameters", {})
    lang = lp.get("defaultLanguage", "en-US")
    title = (lp.get(lang) or {}).get("titleName", "")
    cid = meta.get("contentId", "")
    cn = meta.get("applicationCategoryType")
    ptype = "Application (APP)" if cn == 0 else (f"Type {cn}" if cn is not None else "-")
    drm = meta.get("applicationDrmType", "")
    extra = [("Title ID", meta.get("titleId", "")),
             ("Content ID", cid),
             ("Region", content_region(cid)),
             ("Type", ptype),
             ("Content Ver", meta.get("contentVersion", "")),
             ("Master Ver", meta.get("masterVersion", "")),
             ("Concept ID", meta.get("conceptId", "")),
             ("Min. System", fmt_fw(meta.get("requiredSystemSoftwareVersion"))),
             ("DRM", str(drm).capitalize() if drm else "-"),
             ("SDK", fmt_fw(meta.get("sdkVersion")))]
    return title, extra


def parse_pkg(path):
    if os.path.isdir(path):
        if _ps3_folder_base(path):
            return parse_ps3_folder(path)
        return parse_app_folder(path)
    size = os.path.getsize(path)
    low = path.lower()
    if low.endswith(".ffpfsc"):
        return parse_ffpfsc_image(path)
    if low.endswith(".ffpkg"):
        return parse_ffpkg_image(path)
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic == PS3_MAGIC:
            return parse_ps3_pkg(path)
        if magic != FIH_MAGIC and magic != CNT_MAGIC:
            f.seek(0)
            if f.read(11)[3:11] == b"EXFAT   ":
                return parse_exfat_image(path)
        f.seek(0)
        if magic == FIH_MAGIC:
            hdr = f.read(256)
            emb = u64le(hdr, 0x58)
            signed = hdr[5]
            pfs_off = u64le(hdr, 0x10)
            pfs_size = u64le(hdr, 0x18)
            f.seek(emb)
            chdr = f.read(0x80)
            if chdr[:4] != CNT_MAGIC:
                return parse_ps5_retail_stub(path, size, hdr)
            n = u32be(chdr, 0x10)
            et = u32be(chdr, 0x18)
            cid = chdr[0x40:0x40 + 48].split(b"\x00")[0].decode("ascii", errors="replace")
            ents = parse_cnt_entries(f, emb, n, et)
            nt = read_name_table(f, emb, ents)
            for e in ents:
                e["name"] = entry_name(nt, e["name_off"]) if nt else ""
                e["abs_off"] = emb + e["off"]
            pj = next((e for e in ents if e["name"] == "param.json" or e["id"] == 8192), None)
            meta, title, extra = {}, "", []
            if pj and pj["size"] and pj["size"] < 100_000:
                f.seek(emb + pj["off"])
                try:
                    meta = json.loads(f.read(pj["size"]).decode("utf-8"))
                    title, extra = _param_json_meta(meta)
                except Exception as e:
                    meta = {"_error": str(e)}
            rows = [("Platform", "PS5 (finalized FIH)"),
                    ("Package", "OFC (Official)" if signed == 0x80 else "FPKG (Fake)"),
                    ("Signature", "official" if signed == 0x80 else "debug / fake"),
                    ("Size", fmt_size(size)),
                    ("PFS image", f"{fmt_size(pfs_size)} @ {pfs_off:#x}"),
                    ("Entries", str(len(ents)))]
            rows += extra
            if not any(k == "Content ID" for k, _ in rows):
                rows.insert(2, ("Content ID", cid))
            return {"ok": True, "kind": "ps5", "path": path, "size": size,
                    "title": title or os.path.basename(path),
                    "rows": rows, "entries": ents, "meta": meta, "icon_entry": "icon0.png",
                    "patch_tid": meta.get("titleId", "") if isinstance(meta, dict) else "",
                    "own_ver": meta.get("contentVersion", "") if isinstance(meta, dict) else ""}
        elif magic == CNT_MAGIC:
            hdr = f.read(0x500)
            n = u32be(hdr, 0x10)
            sc = struct.unpack_from(">H", hdr, 0x14)[0]
            et = u32be(hdr, 0x18)
            body_off = u64be(hdr, 0x20)
            cid = hdr[0x40:0x40 + 48].split(b"\x00")[0].decode("ascii", errors="replace")
            ents = parse_cnt_entries(f, 0, n, et)
            nt = read_name_table(f, 0, ents)
            for e in ents:
                e["name"] = entry_name(nt, e["name_off"]) if nt else ""
                e["abs_off"] = e["off"]
            sfo_entry = next((e for e in ents if e["id"] == 4096 or e["name"] == "param.sfo"), None)
            sfo = {}
            if sfo_entry and sfo_entry["size"]:
                f.seek(sfo_entry["off"])
                sfo = parse_sfo(f.read(sfo_entry["size"]))
            pj = next((e for e in ents if e["name"] == "param.json" or e["id"] == 8192), None)
            meta, title, extra = {}, "", []
            _ver4 = ""
            if sfo and not sfo.get("_error"):
                title = sfo.get("TITLE", "")
                _cid4 = sfo.get("CONTENT_ID", cid)
                _cat4 = sfo.get("CATEGORY", "")
                # update PKGs (gp): VERSION = base it applies to,
                # APP_VER = the actual patch version -> show APP_VER
                _ver4 = sfo.get("VERSION", "")
                if str(_cat4).lower() == "gp" and sfo.get("APP_VER"):
                    _ver4 = sfo.get("APP_VER")
                extra = [("Title ID", sfo.get("TITLE_ID", "")),
                         ("Content ID", _cid4),
                         ("Region", content_region(_cid4)),
                         ("Type", ps4_pkg_type(_cat4)),
                         ("Version", _ver4),
                         ("Min. System", str(sfo.get("SYSTEM_VER", "-")))]
            elif pj and pj["size"] and pj["size"] < 100_000:
                f.seek(pj["off"])
                try:
                    meta = json.loads(f.read(pj["size"]).decode("utf-8"))
                    title, extra = _param_json_meta(meta)
                except Exception as e:
                    meta = {"_error": str(e)}
            kind = "PS4" if sfo and not sfo.get("_error") else "CNT"
            rows = [("Platform", f"{kind} (CNT metadata)"),
                    ("Package", cnt_package_type(hdr)),
                    ("Content ID", sfo.get("CONTENT_ID", cid) if sfo else cid),
                    ("Size", fmt_size(size)),
                    ("Entries", f"{n} ({sc} sys)"),
                    ("Body", f"@ {body_off:#x}")]
            rows += extra
            return {"ok": True, "kind": "ps4", "path": path, "size": size,
                    "title": title or os.path.basename(path),
                    "rows": rows, "entries": ents, "meta": meta or sfo,
                    "icon_entry": "icon0.png",
                    "patch_tid": sfo.get("TITLE_ID", "") if isinstance(sfo, dict) else "",
                    "own_ver": _ver4 if sfo and not sfo.get("_error") else ""}
        else:
            # split retail part without header? resolve via sibling _0.
            stub = _split_part_stub(path, size)
            if stub:
                return stub
            return {"error": f"unknown magic {magic!r}"}


# ---------------- PS3 NPDRM PKG (verified: Doodle God retail + 2 debug FIX) ----------------

def _ps3_debug_keystream(qa, block_index):
    import hashlib
    qa0, qa1 = qa[:8], qa[8:16]
    buf = bytearray(64)
    buf[0:8] = qa0
    buf[8:16] = qa0
    buf[16:24] = qa1
    buf[24:32] = qa1
    buf[56:64] = struct.pack(">Q", block_index)
    return hashlib.sha1(bytes(buf)).digest()[:16]


def _ps3_decrypt(f, data_off, retail, keymat, pos, size):
    """Decrypt a data-stream range (offsets relative to data_off). b"" on failure."""
    if size <= 0 or pos < 0:
        return b""
    bs = pos & ~0xF
    pre = pos - bs
    nb = (pre + size + 15) // 16
    if nb > 1 << 24:
        return b""
    f.seek(data_off + bs)
    enc = f.read(nb * 16)
    if len(enc) < nb * 16:
        return b""
    out = bytearray()
    if not retail:
        bi = bs // 16
        for i in range(nb):
            ks = _ps3_debug_keystream(keymat, bi + i)
            out += bytes(a ^ b for a, b in zip(enc[i * 16:(i + 1) * 16], ks))
    else:
        if not HAS_PS3_AES:
            return b""
        e = _Cipher(_Algos.AES(PS3_KEY), _Modes.ECB()).encryptor()
        ctr0 = (int.from_bytes(keymat, "big") + bs // 16) & ((1 << 128) - 1)
        for i in range(nb):
            ks = e.update(((ctr0 + i) & ((1 << 128) - 1)).to_bytes(16, "big"))
            out += bytes(a ^ b for a, b in zip(enc[i * 16:(i + 1) * 16], ks))
    return bytes(out[pre:pre + size])


PS3_TID_REGION = {"NPEB": "Europe", "BCES": "Europe", "NPHB": "Asia",
                  "BCAS": "Asia", "NPJB": "Japan", "BCJS": "Japan",
                  "NPUB": "Americas", "BCUS": "Americas"}


def _ps3_title_id_from_cid(cid):
    try:
        return cid.split("-")[1].split("_")[0]
    except Exception:
        return ""


def _ps3_folder_base(path):
    """Root of PS3 game data: dir itself (NPDRM extract) or PS3_GAME/ (disc extract). '' = not PS3."""
    if os.path.isfile(os.path.join(path, "PS3_GAME", "PARAM.SFO")):
        return os.path.join(path, "PS3_GAME")
    if os.path.isfile(os.path.join(path, "PARAM.SFO")) and any(
            os.path.exists(os.path.join(path, d)) for d in
            ("USRDIR", "TROPDIR", "PS3_GAME", "PS3_UPDATE")):
        return path
    return ""


def parse_ps3_folder(path):
    base = _ps3_folder_base(path)
    sfo = {}
    try:
        with open(os.path.join(base, "PARAM.SFO"), "rb") as fh:
            raw = fh.read(1_000_000)
        if raw[:4] == b"\x00PSF":
            sfo = parse_sfo(raw)
    except OSError:
        pass
    total, nfiles = 0, 0
    for _dp, _dn, fns in os.walk(path):
        nfiles += len(fns)
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(_dp, fn))
            except OSError:
                pass
    title = sfo.get("TITLE", "") if sfo else ""
    tid = (sfo.get("TITLE_ID", "") if sfo else "") or os.path.basename(path.rstrip("/\\"))
    ver = sfo.get("VERSION", "") or sfo.get("APP_VER", "") if sfo else ""
    rows = [("Platform", "PS3 folder"),
            ("Title ID", sfo.get("TITLE_ID", "-") if sfo else "-"),
            ("Region", PS3_TID_REGION.get(
                ((sfo.get("TITLE_ID", "") if sfo else "") or "")[:4].upper(), "-")),
            ("Version", ver or "-"),
            ("Min. System", sfo.get("PS3_SYSTEM_VER", "-") if sfo else "-"),
            ("Size", f"{fmt_size(total)} ({nfiles} files)")]
    ents, _eid = [], 0
    try:
        for fn in sorted(os.listdir(base)):
            if not fn.lower().endswith(".png"):
                continue
            fp = os.path.join(base, fn)
            if not os.path.isfile(fp):
                continue
            try:
                sz = os.path.getsize(fp)
            except OSError:
                continue
            if sz <= 0:
                continue
            ents.append({"id": _eid, "name": fn, "size": sz,
                         "abs_off": -1, "local_path": fp})
            _eid += 1
    except OSError:
        pass
    # PS3 trophy packs (TROPDIR/NPWRxxxxx_00/TROPHY.TRP) for the Trophies tab
    try:
        _tropdir = os.path.join(base, "TROPDIR")
        if os.path.isdir(_tropdir):
            for _np in sorted(os.listdir(_tropdir)):
                _npd = os.path.join(_tropdir, _np)
                if not os.path.isdir(_npd):
                    continue
                for _fn in sorted(os.listdir(_npd)):
                    if not _fn.lower().endswith(".trp"):
                        continue
                    _fp = os.path.join(_npd, _fn)
                    if not os.path.isfile(_fp):
                        continue
                    try:
                        _sz = os.path.getsize(_fp)
                    except OSError:
                        continue
                    if _sz <= 0 or _sz >= 300_000_000:
                        continue
                    ents.append({"id": _eid, "name": f"TROPDIR/{_np}/{_fn}",
                                 "size": _sz, "abs_off": -1,
                                 "local_path": _fp})
                    _eid += 1
    except OSError:
        pass
    icon = next((e["name"] for e in ents if e["name"].upper() == "ICON0.PNG"), "")
    return {"ok": True, "kind": "ps3", "path": path, "size": total,
            "title": title or tid,
            "rows": rows, "entries": ents, "meta": sfo,
            "icon_entry": icon or "icon0.png"}


def _split_part_stub(path, size):
    """Part N>0 of a split set: reuse sibling _0 header to confirm, then stub."""
    import re as _re
    m = _re.search(r"^(.*)_\d+\.pkg$", os.path.basename(path), _re.IGNORECASE)
    if not m:
        return None
    p0 = os.path.join(os.path.dirname(path), m.group(1) + "_0.pkg")
    try:
        with open(p0, "rb") as f:
            mg = f.read(4)
            if mg == CNT_MAGIC:
                return _split_part_ps4(path, size, p0)
            if mg != FIH_MAGIC:
                return None
            hdr = f.read(252)
    except OSError:
        return None
    return parse_ps5_retail_stub(path, size, mg + hdr)


def _split_part_ps4(path, size, p0):
    """PS4 split part: metadata lives in _0 — parse it, relabel part/size."""
    import glob as _glob
    import re as _re
    r = parse_pkg(p0)
    if not r.get("ok"):
        return r
    base = os.path.basename(path)
    sibs = sorted(_glob.glob(os.path.join(os.path.dirname(path), base.rsplit("_", 1)[0] + "_*.pkg")))
    sibs = [p for p in sibs if _re.search(r"_\d+\.pkg$", p, _re.IGNORECASE)]
    sibs.sort(key=lambda p: int(_re.search(r"_(\d+)\.pkg$", p, _re.IGNORECASE).group(1)))
    idx = next((i for i, p in enumerate(sibs) if os.path.basename(p) == base), 0)
    try:
        total = sum(os.path.getsize(p) for p in sibs) if len(sibs) > 1 else size
    except OSError:
        total = size
    rows = []
    for k, v in r["rows"]:
        if k == "Size":
            v = f"{fmt_size(size)} (joined {fmt_size(total)})"
        rows.append((k, v))
    rows.append(("Part", f"{idx + 1} of {len(sibs)}" if len(sibs) > 1 else "single"))
    r["rows"] = rows
    return r


_STORE_CACHE = {}
_STORE_LOCALE = {"UP": "en-us", "EP": "en-gb", "JP": "ja-jp", "HP": "en-hk"}


_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_NET_DOWN_UNTIL = {}


def _host_up(host, port=443, timeout=3, cache=60):
    """Fast offline check: True if TCP connects. Failures cached `cache` s
    so offline mode never hangs on full HTTP timeouts. Never raises."""
    import socket as _so
    import time as _tm
    now = _tm.time()
    k = (host, port)
    try:
        if _NET_DOWN_UNTIL.get(k, 0) > now:
            return False
    except Exception:
        pass
    try:
        _so.create_connection((host, port), timeout=timeout).close()
        return True
    except Exception:
        try:
            _NET_DOWN_UNTIL[k] = now + cache
        except Exception:
            pass
        return False


def fetch_store_cover(cid):
    """(name, cover_url, release, tagline) from PlayStation Store. Square MASTER art preferred."""
    import re as _re
    import urllib.request as _ureq
    if not cid or "-" not in cid:
        return None, None, None, None
    if cid in _STORE_CACHE:
        return _STORE_CACHE[cid]
    if not _host_up("store.playstation.com"):
        return None, None, None, None
    loc = _STORE_LOCALE.get(cid.split("-")[0][:2].upper(), "en-us")
    url = "https://store.playstation.com/%s/product/%s" % (loc, cid)
    try:
        req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", "replace")
    except Exception:
        _STORE_CACHE[cid] = (None, None, None, None)
        return None, None, None, None
    arts = {}
    for m in _re.finditer(r'"role":"([A-Z_0-9]+)"[^}]{0,400}?"url":"(https://[^"]+)"', html):
        arts.setdefault(m.group(1), m.group(2))
    for m in _re.finditer(r'"url":"(https://[^"]+)"[^}]{0,400}?"role":"([A-Z_0-9]+)"', html):
        arts.setdefault(m.group(2), m.group(1))
    cover = arts.get("MASTER") or arts.get("GAMEHUB_COVER_ART")
    mn = _re.search(r'"__typename":"Concept","name":"([^"]+)"', html)
    name = mn.group(1) if mn else None
    mr = _re.search(r'"releaseDate":"(\d{4}-\d{2}-\d{2})', html)
    rel = mr.group(1) if mr else None
    md = _re.search(r'"description":"([^"]{10,160})"', html)
    tag = md.group(1) if md else None
    _STORE_CACHE[cid] = (name, cover, rel, tag)
    return name, cover, rel, tag


def download_url_bytes(url, timeout=30):
    import urllib.request as _ureq
    req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _ureq.urlopen(req, timeout=timeout) as r:
        return r.read()


_PATCH_CACHE = {}
_PATCH_HOST = {"PPSA": "https://prosperopatches.com",
               "CUSA": "https://orbispatches.com"}


def _ago(date_str):
    """'2024-11-21...' -> '8 mo ago'. '' on parse failure."""
    import datetime as _dt
    import re as _re
    m = _re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str or "")
    if not m:
        return ""
    try:
        d = _dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        days = (_dt.date.today() - d).days
    except ValueError:
        return ""
    if days < 0:
        return ""
    if days == 0:
        return "today"
    if days < 30:
        return f"{days} day{'s' if days > 1 else ''} ago"
    months = days // 30
    if months < 12:
        return f"{months} mo ago"
    years = months // 12
    rem = months % 12
    return f"{years}y {rem}m ago" if rem else f"{years}y ago"


def fetch_latest_patch(tid):
    """(latest_ver, patch_count, date_str) from patch trackers. Cached per session."""
    import json as _json
    import re as _re
    import urllib.request as _ureq
    if not tid:
        return None, 0, ""
    tid = tid.upper()
    if tid in _PATCH_CACHE:
        return _PATCH_CACHE[tid]
    host = _PATCH_HOST.get(tid[:4])
    if not host:
        _PATCH_CACHE[tid] = (None, 0, "")
        return None, 0, ""
    import urllib.parse as _up
    try:
        if not _host_up(_up.urlparse(host).hostname or ""):
            return None, 0, ""
    except Exception:
        return None, 0, ""
    try:
        req = _ureq.Request(host + "/" + tid, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", "replace")
        m = _re.search(r'dynpatch"\s+data-titleid="%s"\s+data-key="([0-9a-f]{64})"' % tid, html)
        if not m:
            m = _re.search(r"data-loadparams=\"\{\s*'titleid':\s*'%s',\s*'key':\s*'([0-9a-f]{64})'" % tid, html)
        if not m:
            m = _re.search(r'data-key="([0-9a-f]{64})"', html)
        if not m:
            _PATCH_CACHE[tid] = (None, 0, "")
            return None, 0, ""
        body = _json.dumps({"titleid": tid, "key": m.group(1)}).encode()
        req2 = _ureq.Request(host + "/api/internal/loadpatches", data=body,
                             headers={"User-Agent": "Mozilla/5.0",
                                      "Content-Type": "application/json"})
        with _ureq.urlopen(req2, timeout=10) as r2:
            j = _json.loads(r2.read())
        patches = j.get("patches", []) if j.get("success") else []
        pick = next((p for p in patches if p.get("is_latest")), None)
        if not pick and patches:
            pick = patches[0]
        latest = (pick.get("content_ver") or pick.get("version")) if pick else None
        date = (pick.get("import_date") or pick.get("creation_date") or "") if pick else ""
        _PATCH_CACHE[tid] = (latest, len(patches), date)
        return latest, len(patches), date
    except Exception:
        _PATCH_CACHE[tid] = (None, 0, "")
        return None, 0, ""


def parse_ps5_retail_stub(path, size, hdr):
    """Retail (encrypted) PS5 PKG: metadata unreadable. Info from filename + split set."""
    import glob as _glob
    import re as _re
    base = os.path.basename(path)
    m = _re.search(r"([A-Z]{2}\d{3,4}-[A-Z]{4}\d{5}_[0-9A-Z\-]+)", base)
    cid = m.group(1) if m else ""
    tid = _ps3_title_id_from_cid(cid) if cid else ""
    parts, total = [path], size
    m2 = _re.search(r"^(.*)_\d+\.pkg$", base, _re.IGNORECASE)
    if m2:
        sibs = sorted(_glob.glob(os.path.join(os.path.dirname(path), m2.group(1) + "_*.pkg")))
        sibs = [p for p in sibs if _re.search(r"_\d+\.pkg$", p, _re.IGNORECASE)]
        sibs.sort(key=lambda p: int(_re.search(r"_(\d+)\.pkg$", p, _re.IGNORECASE).group(1)))
        if len(sibs) > 1:
            parts = sibs
            try:
                total = sum(os.path.getsize(p) for p in parts)
            except OSError:
                pass
    idx = next((i for i, p in enumerate(parts)
                if os.path.basename(p) == base), 0)
    rows = [("Platform", "PS5 retail (encrypted)"),
            ("Package", "OFC (Official)" if len(hdr) > 5 and hdr[5] == 0x80
             else "FPKG (Fake)"),
            ("Content ID", cid or "-"),
            ("Title ID", tid or "-"),
            ("Region", content_region(cid)),
            ("Part", f"{idx + 1} of {len(parts)}" if len(parts) > 1 else "single"),
            ("Size", f"{fmt_size(size)} (joined {fmt_size(total)})" if len(parts) > 1
             else fmt_size(size)),
            ("Note", "metadata encrypted — title/files unavailable")]
    return {"ok": True, "kind": "ps5", "path": path, "size": size,
            "title": tid or base, "rows": rows, "entries": [],
            "meta": {}, "icon_entry": "icon0.png", "store_cid": cid or "",
            "patch_tid": tid or "", "own_ver": ""}


def parse_ps3_pkg(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        hdr = f.read(128)
        if len(hdr) < 128:
            return {"error": "too small for PS3 PKG"}
        magic, rev, typ, _mo, _mc, _hs, n, _tot, doff, dsz, cidraw, qa, riv = \
            struct.unpack(PS3_HDR_FMT, hdr)
        if magic != PS3_MAGIC:
            return {"error": "bad PS3 magic"}
        if typ != 1:
            return {"error": f"not PS3 NPDRM (type {typ:#x})"}
        cid = cidraw.split(b"\x00")[0].decode("ascii", errors="replace")
        retail = (rev == 0x8000)
        keymat = riv if retail else qa
        sfo, ents = {}, []
        if n and n < 1_000_000 and doff and dsz:
            try:
                tab = _ps3_decrypt(f, doff, retail, keymat, 0, n * 32)
                if len(tab) == n * 32:
                    recs = []
                    for i in range(n):
                        no, ns, fo, fs, fl, _pad = struct.unpack_from(PS3_ITEM_FMT, tab, i * 32)
                        if ns > dsz or no + ns > dsz or fo + fs > dsz:
                            continue
                        nm = ""
                        if ns:
                            nm = _ps3_decrypt(f, doff, retail, keymat, no, ns)
                            nm = nm.rstrip(b"\x00").decode("utf-8", errors="replace")
                        recs.append((nm, fo, fs, fl))
                    for i, (nm, fo, fs, fl) in enumerate(recs):
                        if not nm:
                            continue
                        ents.append({"id": i, "name": nm, "size": fs,
                                     "abs_off": ("ps3", retail, keymat, doff, fo)})
                    for nm, fo, fs, _fl in recs:
                        if nm.upper().endswith("PARAM.SFO") and 0 < fs < 1_000_000:
                            raw = _ps3_decrypt(f, doff, retail, keymat, fo, fs)
                            if raw[:4] == b"\x00PSF":
                                sfo = parse_sfo(raw)
                            break
            except Exception:
                pass
    title = sfo.get("TITLE", "") if sfo else ""
    tid = (sfo.get("TITLE_ID", "") if sfo else "") or _ps3_title_id_from_cid(cid)
    ver = ""
    if sfo:
        ver = sfo.get("VERSION", "") or sfo.get("APP_VER", "")
    rows = [("Platform", "PS3 NPDRM (%s)" % ("retail" if retail else "debug")),
            ("Content ID", cid or "-"),
            ("Title ID", tid or "-"),
            ("Region", content_region(cid) if "-" in (cid or "")
             else PS3_TID_REGION.get((tid or "")[:4].upper(), "-")),
            ("Version", ver or "-"),
            ("Min. System", sfo.get("PS3_SYSTEM_VER", "-") if sfo else "-"),
            ("Size", fmt_size(size)),
            ("Files", str(len(ents)) if ents else f"{n} (encrypted)")]
    if not ents:
        rows.append(("Note", "listing unavailable (AES lib missing)" if retail and not HAS_PS3_AES
                     else "file table unreadable"))
    icon = next((e["name"] for e in ents if e["name"].upper() == "ICON0.PNG"), "")
    return {"ok": True, "kind": "ps3", "path": path, "size": size,
            "title": title or tid or os.path.basename(path),
            "rows": rows, "entries": ents, "meta": sfo,
            "icon_entry": icon or "icon0.png"}


# AMPR/LZ4 asset containers (LIZARD-style PS5 app dumps: AMPRPAK4/AMPRDAT3/...)
AMPR_MAGICS = (b"AMPRPAK4", b"AMPRDAT3", b"AMPRIDX3", b"AMPRCRC1", b"AMPRCFG1")
_UNITY_SIG = b"UnityFS\x00"
_UNITY_COMP = {0: "raw", 1: "LZMA", 2: "LZ4", 3: "LZ4HC"}
_UNITY_MARKERS = (b"2022.3.57f1", b"CAB-", b"AssetBundle", b".resS",
                  b"globalgamemanagers")


def _unity_comp_at(buf, pos):
    """Parse a UnityFS header at buf-relative pos → comp name or ''."""
    try:
        p = pos + 8 + 4
        e1 = buf.find(b"\x00", p)
        if e1 < 0:
            return ""
        e2 = buf.find(b"\x00", e1 + 1)
        if e2 < 0:
            return ""
        p = e2 + 1 + 8 + 4 + 4
        fl = struct.unpack_from(">I", buf, p)[0]
        return _UNITY_COMP.get(fl & 0x3F, "")
    except Exception:
        return ""


def _probe_pak_lz4(fp, size):
    """Strided probe of an AMPR .pak → 'LZ4HC' / 'LZ4' / 'Unity' / ''.

    Reads 1MB windows every 16MB (small files read fully), parses any
    UnityFS header (flags&0x3F: 2=LZ4, 3=LZ4HC), else falls back to lz4
    tokens / Unity bundle markers. Early-exits on LZ4HC.
    """
    try:
        f = open(fp, "rb")
    except OSError:
        return ""
    comps = []
    seen_lz4 = False
    seen_unity = False
    try:
        if size <= 32 << 20:
            offs = [0]
            wn = int(size)
        else:
            step = 16 << 20
            wn = 1 << 20
            offs = list(range(0, size - wn + 1, step))
            if offs[-1] != size - wn:
                offs.append(size - wn)
        for off in offs:
            try:
                f.seek(off)
                buf = f.read(wn + 256)
            except OSError:
                continue
            if not buf:
                continue
            i = 0
            while True:
                i = buf.find(_UNITY_SIG, i)
                if i < 0 or len(comps) >= 3:
                    break
                c = _unity_comp_at(buf, i)
                if c:
                    comps.append(c)
                    if c == "LZ4HC":
                        f.close()
                        return "LZ4HC"
                i += 1
            low = buf.lower()
            if b"lz4" in low:
                seen_lz4 = True
            if not seen_unity:
                for m in _UNITY_MARKERS:
                    if m in buf:
                        seen_unity = True
                        break
    finally:
        try:
            f.close()
        except Exception:
            pass
    if any(c == "LZ4" for c in comps):
        return "LZ4"
    if any(c == "LZMA" for c in comps):
        return "LZMA"
    if seen_lz4:
        return "LZ4"
    if seen_unity or comps:
        return "Unity"
    return ""


def _scan_ampr(path):
    """Top-level AMPR container files: [(name, size, magic, codec)] or []."""
    out = []
    try:
        for fn in sorted(os.listdir(path)):
            fp = os.path.join(path, fn)
            if not os.path.isfile(fp):
                continue
            ln = fn.lower()
            if not (ln.startswith("ampr_") or ln.endswith((".pak", ".index",
                                                            ".crc", ".runtime"))):
                continue
            try:
                with open(fp, "rb") as fh:
                    magic = fh.read(8)
            except OSError:
                continue
            if magic in AMPR_MAGICS:
                try:
                    sz = os.path.getsize(fp)
                except OSError:
                    continue
                codec = _probe_pak_lz4(fp, sz) if magic == b"AMPRDAT3" else ""
                out.append((fn, sz, magic.decode("ascii"), codec))
    except OSError:
        pass
    return out


def parse_app_folder(path):
    """PS5 app dump folder: sce_sys/param.json + icon0.png, no container."""
    pj = os.path.join(path, "sce_sys", "param.json")
    icon = os.path.join(path, "sce_sys", "icon0.png")
    meta, title, extra = {}, "", []
    if os.path.isfile(pj):
        try:
            with open(pj, "r", encoding="utf-8") as fh:
                meta = json.load(fh)
            title, extra = _param_json_meta(meta)
        except Exception as e:
            meta = {"_error": str(e)}
    total = 0
    nfiles = 0
    for _dp, _dn, fns in os.walk(path):
        nfiles += len(fns)
        for fn in fns:
            try:
                total += os.path.getsize(os.path.join(_dp, fn))
            except OSError:
                pass
    rows = [("Platform", "PS5 app folder"),
            ("Size", f"{fmt_size(total)} ({nfiles} files)")]
    ampr = _scan_ampr(path)
    if ampr:
        _lz4 = sum(1 for t in ampr if t[3] == "LZ4")
        _hc = sum(1 for t in ampr if t[3] == "LZ4HC")
        _albl = f"{len(ampr)} AMPR containers ({fmt_size(sum(s for _, s, _, _ in ampr))})"
        _codecs = []
        if _lz4:
            _codecs.append(f"LZ4 x{_lz4}" if _lz4 > 1 else "LZ4")
        if _hc:
            _codecs.append(f"LZ4HC x{_hc}" if _hc > 1 else "LZ4HC")
        if _codecs:
            _albl += " \u00b7 " + " \u00b7 ".join(_codecs)
        rows.append(("Assets", _albl))
    rows += extra
    ents = []
    if os.path.isfile(icon):
        try:
            ents.append({"id": 0, "name": "icon0.png", "size": os.path.getsize(icon),
                         "abs_off": -1, "local_path": icon})
        except OSError:
            pass
    # every other PNG in sce_sys (pic0, icon variants, ...) for the gallery
    try:
        _sce = os.path.join(path, "sce_sys")
        _eid = 1
        for _fn in sorted(os.listdir(_sce)):
            if _fn == "icon0.png" or not _fn.lower().endswith(".png"):
                continue
            _fp = os.path.join(_sce, _fn)
            if not os.path.isfile(_fp):
                continue
            try:
                _sz = os.path.getsize(_fp)
            except OSError:
                continue
            if _sz <= 0:
                continue
            ents.append({"id": _eid, "name": _fn, "size": _sz,
                         "abs_off": -1, "local_path": _fp})
            _eid += 1
    except OSError:
        pass
    # trophy packs anywhere in the dump (sce_sys/trophy, Image0, ...)
    # so the Trophies tab auto-fills for folders too
    try:
        _eid = max([e["id"] for e in ents], default=0) + 1
        for _dp, _dn, _fns in os.walk(path):
            for _fn in sorted(_fns):
                _ln = _fn.lower()
                if not (_ln.endswith(".trp") or _ln.endswith(".ucp")):
                    continue
                _fp = os.path.join(_dp, _fn)
                try:
                    _sz = os.path.getsize(_fp)
                except OSError:
                    continue
                if _sz <= 0 or _sz >= 300_000_000:
                    continue
                _rel = os.path.relpath(_fp, path).replace("\\", "/")
                ents.append({"id": _eid, "name": _rel, "size": _sz,
                             "abs_off": -1, "local_path": _fp})
                _eid += 1
    except OSError:
        pass
    # AMPR/LZ4 asset containers in the Files tab (name + size + codec)
    try:
        _eid = max([e["id"] for e in ents], default=0) + 1
        for _fn, _sz, _magic, _codec in ampr:
            _nm = f"{_fn}  [{_codec}]" if _codec else _fn
            ents.append({"id": _eid, "name": _nm, "size": _sz,
                         "abs_off": -1, "local_path": os.path.join(path, _fn),
                         "ampr": _magic, "codec": _codec or "-"})
            _eid += 1
    except OSError:
        pass
    r = {"ok": True, "kind": "ps5", "path": path, "size": total,
         "title": title or os.path.basename(path.rstrip("/\\")),
         "rows": rows, "entries": ents, "meta": meta, "icon_entry": "icon0.png"}
    if ampr:
        r["ampr_lines"] = [f"{_fn} = {_mg}" + (f" / {_cd}" if _cd else "")
                           for _fn, _sz, _mg, _cd in ampr]
    if os.path.isfile(icon):
        r["folder_icon"] = icon
    return r


class _Exfat:
    """Minimal read-only exFAT: boot sector, FAT walk, dir scan."""

    def __init__(self, path_or_file):
        if hasattr(path_or_file, "read"):
            self.path = getattr(path_or_file, "name", "<view>")
            self.f = path_or_file
            self._own = False
            pos = self.f.tell()
            self.f.seek(0, 2)
            self._img_size = self.f.tell()
            self.f.seek(0)
        else:
            self.path = path_or_file
            self.f = open(path_or_file, "rb")
            self._own = True
            self.f.seek(0, 2)
            self._img_size = self.f.tell()
            self.f.seek(0)
        bs = self.f.read(512)
        if bs[3:11] != b"EXFAT   " or bs[510] != 0x55 or bs[511] != 0xAA:
            raise ValueError("not an exFAT image")
        self.bps = 1 << bs[108]
        self.spc = 1 << bs[109]
        self.clus_bytes = self.bps * self.spc
        fat_off = struct.unpack_from("<I", bs, 80)[0]
        data_off = struct.unpack_from("<I", bs, 88)[0]
        root_clus = struct.unpack_from("<I", bs, 96)[0]
        self.fat_sec = fat_off
        self.data_sec = data_off
        self.root_clus = root_clus

    def close(self):
        if getattr(self, "_own", True):
            try:
                self.f.close()
            except Exception:
                pass

    def _clus_off(self, clus):
        return (self.data_sec + (clus - 2) * self.spc) * self.bps

    def _fat_next(self, clus):
        self.f.seek(self.fat_sec * self.bps + clus * 4)
        v = struct.unpack("<I", self.f.read(4))[0]
        return None if v >= 0xFFFFFFF8 else v

    def read_chain(self, first, size):
        out = bytearray()
        clus = first
        while clus is not None and len(out) < size:
            self.f.seek(self._clus_off(clus))
            out += self.f.read(min(self.clus_bytes, size - len(out)))
            nxt = self._fat_next(clus)
            # Builder writes files contiguously but leaves FAT zeroed:
            # fall through to the next cluster instead of stopping.
            clus = nxt if nxt not in (None, 0) else clus + 1
            if self._clus_off(clus) >= self._img_size:
                break
        return bytes(out[:size])

    def _iter_dir(self, first, size, nofat):
        if nofat:
            self.f.seek(self._clus_off(first))
            raw = self.f.read(size)
        else:
            raw = self.read_chain(first, size)
        return raw

    def list_dir(self, first, size, nofat, want=None):
        """List dir entries; if want is set, stop early once found (faster).

        Reads are capped (16MB): a miss must not stream the whole image
        (root scan on a 200GB USB image would take minutes).
        """
        cap = min(size, 1 << 24)
        if nofat:
            self.f.seek(self._clus_off(first))
            raw = self.f.read(min(size, 1 << 20))
            return self._parse_dir(raw, want)
        out = bytearray()
        clus = first
        while clus is not None and len(out) < cap:
            self.f.seek(self._clus_off(clus))
            out += self.f.read(min(self.clus_bytes, size - len(out)))
            if want:
                items = self._parse_dir(bytes(out), want)
                if any(n.lower() == want for n, *_ in items):
                    return items
            nxt = self._fat_next(clus)
            clus = nxt if nxt not in (None, 0) else clus + 1
            if self._clus_off(clus) >= self._img_size:
                break
        return self._parse_dir(bytes(out[:size]), want)

    def _parse_dir(self, raw, want=None):
        items = []
        i = 0
        pending = None
        while i + 32 <= len(raw):
            etype = raw[i]
            if etype == 0x00:
                break
            if etype == 0x85 and i + 32 <= len(raw):
                nsec = raw[i + 1]
                pending = {"attrs": struct.unpack_from("<H", raw, i + 4)[0],
                           "names": [], "nsec": nsec}
            elif etype == 0xC0 and pending is not None:
                flags = struct.unpack_from("<H", raw, i + 2)[0]
                pending["nofat"] = bool(flags & 0x02)
                pending["first"] = struct.unpack_from("<I", raw, i + 20)[0]
                pending["size"] = struct.unpack_from("<Q", raw, i + 24)[0]
            elif etype == 0xC1 and pending is not None:
                chars = struct.unpack_from("<15H", raw, i + 2)
                pending["names"].append("".join(
                    chr(c) for c in chars if c).rstrip("\x00"))
                if len(pending["names"]) >= pending.get("nsec", 1) - 1:
                    name = "".join(pending["names"])
                    items.append((name, pending.get("attrs", 0),
                                  pending.get("first", 0),
                                  pending.get("size", 0),
                                  pending.get("nofat", False)))
                    pending = None
                    if want and name.lower() == want:
                        break
            i += 32
        return items

    def find(self, parts):
        clus, size, nofat = self.root_clus, 1 << 30, False
        for depth, part in enumerate(parts):
            if depth == 0 and (part == "" or part.lower().endswith(".exfat")):
                continue
            found = None
            want = part.lower() if depth < len(parts) else None
            for name, attrs, first, sz, nf in self.list_dir(clus, size, nofat,
                                                            want=want):
                if name.lower() == part.lower():
                    found = (attrs, first, sz, nf)
                    break
            if found is None:
                return None
            attrs, first, sz, nf = found
            if depth == len(parts) - 1:
                return {"first": first, "size": sz, "nofat": nf,
                        "is_dir": bool(attrs & 0x10)}
            if not (attrs & 0x10):
                return None
            clus, size, nofat = first, sz, nf
        return None

    def list_path(self, parts):
        """List names in a subdir given as path parts; [] on error."""
        clus, size, nofat = self.root_clus, 1 << 30, False
        for depth, part in enumerate(parts):
            if depth == 0 and (part == "" or part.lower().endswith(".exfat")):
                continue
            found = None
            want = part.lower() if depth < len(parts) else None
            for name, attrs, first, sz, nf in self.list_dir(clus, size, nofat,
                                                            want=want):
                if name.lower() == part.lower():
                    found = (attrs, first, sz, nf)
                    break
            if found is None:
                return []
            attrs, first, sz, nf = found
            if depth == len(parts) - 1:
                if not (attrs & 0x10):
                    return []
                return [{"name": n, "first": f, "size": s, "nofat": nf2,
                         "is_dir": bool(a & 0x10)}
                        for n, a, f, s, nf2 in self.list_dir(first, sz, nf)]
            if not (attrs & 0x10):
                return []
            clus, size, nofat = first, sz, nf
        return []


def _open_ffpfsc_view(path):
    """Open inner exFAT view of an .ffpfsc via mkpfs. Returns (view, fh, name).

    Caller must close fh. Raises RuntimeError if mkpfs is missing.
    """
    try:
        from pathlib import Path as _P
        from mkpfs.pfs import open_inner_file_view as _oiv
    except ImportError:
        raise RuntimeError("mkpfs not installed (pip install mkpfs)")
    r = _oiv(_P(path))
    if not r:
        raise ValueError("no single inner file in ffpfsc")
    return r


def parse_exfat_image(path):
    """PS5 exFAT game image: pull sce_sys/param.json + icon0.png via FAT walk."""
    size = os.path.getsize(path)
    fs = _Exfat(path)
    try:
        return _exfat_result(fs, path, size, "PS5 exFAT image")
    finally:
        fs.close()


def parse_ffpfsc_image(path):
    """Compressed PFS (.ffpfsc): open inner exFAT via mkpfs, then FAT walk."""
    size = os.path.getsize(path)
    view, fh, inner = _open_ffpfsc_view(path)
    try:
        fs = _Exfat(view)
        try:
            r = _exfat_result(fs, path, size, "PS5 ffpfsc image",
                              inner_name=inner)
        finally:
            fs.close()
        # Cache the icon bytes now; the PFS view closes with fh.
        for e in r.get("entries", []):
            try:
                fs2 = _Exfat(view)
                try:
                    first = e["abs_off"][1]
                    fsize = e["abs_off"][2]
                    nofat = e["abs_off"][3]
                    if nofat:
                        fs2.f.seek(fs2._clus_off(first))
                        e["cached"] = fs2.f.read(fsize)
                    else:
                        e["cached"] = fs2.read_chain(first, fsize)
                finally:
                    fs2.close()
            except Exception:
                pass
            e["abs_off"] = -2
        return r
    finally:
        try:
            fh.close()
        except Exception:
            pass


def parse_ffpkg_image(path):
    """UFS2 game image (.ffpkg): read sce_sys/param.json + PNGs via pytsk3.

    All PNG bytes are cached in memory so the image handle closes
    immediately (like ffpfsc). Raises informative error if pytsk3 missing.
    """
    size = os.path.getsize(path)
    try:
        import pytsk3
    except ImportError:
        return {"error": "pytsk3 not installed (pip install pytsk3) - needed for .ffpkg"}
    img = pytsk3.Img_Info(path)
    try:
        fs = pytsk3.FS_Info(img)
    except Exception as e:
        return {"error": f"not a filesystem image: {e}"}
    try:
        return _ffpkg_read(fs, path, size)
    finally:
        try:
            img.close()
        except Exception:
            pass


def _ffpkg_read(fs, path, size):
    """Read param.json + PNGs from an open pytsk3 FS. Caller closes img."""
    try:
        _pjf = fs.open("/sce_sys/param.json")
        _pjsz = _pjf.info.meta.size if _pjf.info.meta else 0
        if _pjsz <= 0 or _pjsz > 100_000:
            return {"error": "sce_sys/param.json bad size"}
        raw = _pjf.read_random(0, _pjsz)
    except Exception as e:
        return {"error": f"sce_sys/param.json not found: {e}"}
    try:
        meta = json.loads(raw.decode("utf-8"))
    except Exception as e:
        return {"error": f"bad param.json: {e}"}
    title, extra = _param_json_meta(meta)
    ents = []
    try:
        d = fs.open_dir(path="/sce_sys")
        names = []
        for e in d:
            try:
                nm = e.info.name.name.decode()
            except Exception:
                continue
            if nm in (".", ".."):
                continue
            if not nm.lower().endswith(".png"):
                continue
            sz = e.info.meta.size if e.info.meta else 0
            if sz <= 0 or sz > 32_000_000:
                continue
            names.append((nm, sz))
    except Exception:
        names = []
    names.sort(key=lambda t: (t[0] != "icon0.png", t[0]))
    for i, (nm, sz) in enumerate(names):
        try:
            data = fs.open("/sce_sys/" + nm).read_random(0, sz)
        except Exception:
            continue
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            continue
        ents.append({"id": i, "name": nm, "size": len(data),
                     "abs_off": -2, "cached": bytes(data)})
    rows = [("Platform", "PS5 ffpkg image"),
            ("Size", fmt_size(size))] + extra
    return {"ok": True, "kind": "ps5", "path": path, "size": size,
            "title": title or os.path.basename(path),
            "rows": rows, "entries": ents, "meta": meta,
            "icon_entry": "icon0.png", "ffpkg": True}


def _exfat_scan_packs(fs, max_dirs=500):
    """Find trophy packs (.trp/.ucp) anywhere in an exFAT image.

    Fast path first: the known trophy dirs (direct lookup, no walk).
    Full directory walk only as fallback (slow on big USB images).
    Directory walk only (no file data read): [(relpath, first, size,
    nofat)]. Never raises.
    """
    out = []
    try:
        for _cand in (["sce_sys", "trophy"], ["sce_sys", "trophy2"],
                      ["trophy"], ["trophy2"]):
            try:
                for _it in fs.list_path(_cand):
                    if _it["is_dir"]:
                        continue
                    _ln = _it["name"].lower()
                    if ( _ln.endswith(".trp") or _ln.endswith(".ucp")) \
                            and 0 < _it["size"] < 300_000_000:
                        out.append(("/".join(_cand + [_it["name"]]),
                                    _it["first"], _it["size"], _it["nofat"]))
            except Exception:
                continue
        if out:
            return out
        stack = [([], fs.root_clus, 1 << 30, False)]
        seen = 0
        while stack and seen < max_dirs:
            parts, clus, size, nofat = stack.pop()
            seen += 1
            try:
                items = fs.list_dir(clus, size, nofat)
            except Exception:
                continue
            for name, attrs, first, sz, nf in items:
                if not name or name in (".", ".."):
                    continue
                if attrs & 0x10:
                    if len(parts) < 5:
                        stack.append((parts + [name], first, sz, nf))
                else:
                    ln = name.lower()
                    if (ln.endswith(".trp") or ln.endswith(".ucp")) \
                            and 0 < sz < 300_000_000:
                        out.append(("/".join(parts + [name]), first, sz, nf))
    except Exception:
        pass
    return out


def _exfat_result(fs, path, size, platform, inner_name=None):
    pj = fs.find(["sce_sys", "param.json"])
    meta, title, extra = {}, "", []
    if pj and not pj["is_dir"] and pj["size"] < 100_000:
        try:
            if pj["nofat"]:
                fs.f.seek(fs._clus_off(pj["first"]))
                raw = fs.f.read(pj["size"])
            else:
                raw = fs.read_chain(pj["first"], pj["size"])
            meta = json.loads(raw.decode("utf-8"))
            title, extra = _param_json_meta(meta)
        except Exception as e:
            meta = {"_error": str(e)}
    icon = fs.find(["sce_sys", "icon0.png"])
    ents = []
    if icon and not icon["is_dir"] and icon["size"] > 0:
        ents.append({"id": 0, "name": "icon0.png", "size": icon["size"],
                     "abs_off": ("exfat", icon["first"], icon["size"],
                                 icon["nofat"])})
    # every other PNG in sce_sys (pic0, icon variants, ...) for the gallery
    try:
        _seen = {"icon0.png"}
        _eid = 1
        for _it in fs.list_path(["sce_sys"]):
            _nm = _it["name"]
            if (_it["is_dir"] or _nm in _seen or not _nm.lower().endswith(".png")
                    or _it["size"] <= 0 or _it["size"] > 32_000_000):
                continue
            _seen.add(_nm)
            ents.append({"id": _eid, "name": _nm, "size": _it["size"],
                         "abs_off": ("exfat", _it["first"], _it["size"],
                                     _it["nofat"])})
            _eid += 1
    except Exception:
        pass
    # trophy packs anywhere in the image (sce_sys/trophy, ...) for the
    # Trophies tab — read on demand via the exfat tuple reader
    try:
        for _rel, _first, _sz, _nf in _exfat_scan_packs(fs):
            ents.append({"id": _eid, "name": _rel, "size": _sz,
                         "abs_off": ("exfat", _first, _sz, _nf)})
            _eid += 1
    except Exception:
        pass
    rows = [("Platform", platform),
            ("Size", fmt_size(size))]
    if inner_name:
        rows.append(("Inner file", inner_name))
    rows += extra
    return {"ok": True, "kind": "ps5", "path": path, "size": size,
            "title": title or os.path.basename(path),
            "rows": rows, "entries": ents, "meta": meta,
            "icon_entry": "icon0.png", "exfat": True}


def parse_trp(data):
    """Inner files of a trophy00.trp (PS4/PS5): [{name, off, size}] or [].

    Layout (verified on retail TRP): u32 magic DCA24D00, u32be count @4,
    u64be total @8, u32be header 0x4d @0x10, u32be entry-size 0x40 @0x14,
    32-byte digest @0x18, entries @0x38: {u64 unk, u64be off, u64be size,
    u64 flags, u64 unk, char name[24]}. Strict validation — [] on doubt.
    """
    try:
        if not data or len(data) < 0x38 or data[:4] != b"\xdc\xa2M\x00":
            return []
        import struct as _st
        count = _st.unpack_from(">I", data, 4)[0]
        total = _st.unpack_from(">Q", data, 8)[0]
        esize = _st.unpack_from(">I", data, 0x14)[0]
        if not (1 <= count <= 10000) or total != len(data):
            return []
        if esize != 0x40:
            return []
        hsize = 0x38  # entries start after the 32-byte digest
        out = []
        for i in range(count):
            eo = hsize + i * esize
            if eo + esize > len(data):
                return []
            off = _st.unpack_from(">Q", data, eo + 8)[0]
            size = _st.unpack_from(">Q", data, eo + 16)[0]
            nm = data[eo + 40:eo + 64].split(b"\x00")[0].decode(
                "ascii", errors="replace")
            if not nm or off + size > len(data):
                return []
            out.append({"name": nm, "off": off, "size": size})
        return out
    except Exception:
        return []


# PS4/PS5 trophy ESFM decryption (psdevwiki: public Trophy_Key; per-title
# NPcommID like NPWR13863_00). Verified on L.A. Noire DUPLEX dump.
TRP_TROPHY_KEY = bytes([0x21, 0xF4, 0x1A, 0x6B, 0xAD, 0x8A, 0x1D, 0x3E,
                        0xCA, 0x7A, 0xD5, 0x86, 0xC1, 0x01, 0xB7, 0xA9])


def decrypt_esfm(blob, npcommid):
    """Decrypt one ESFM file -> XML bytes, or None. Never raises."""
    try:
        from cryptography.hazmat.primitives.ciphers import (
            Cipher as _Cipher, algorithms as _Algos, modes as _Modes)
    except Exception:
        return None
    try:
        if not blob or len(blob) < 32 or len(blob) % 16:
            return None
        npid = (npcommid.encode()[:16]
                if isinstance(npcommid, str) else bytes(npcommid[:16]))
        npid = npid.ljust(16, b"\x00")
        enc = _Cipher(_Algos.AES(TRP_TROPHY_KEY),
                      _Modes.CBC(bytes(16))).encryptor()
        ckey = enc.update(npid) + enc.finalize()
        dec = _Cipher(_Algos.AES(ckey), _Modes.CBC(blob[:16])).decryptor()
        pt = dec.update(blob[16:]) + dec.finalize()
        pad = pt[-1]
        if not (1 <= pad <= 16) or pt[-pad:] != bytes([pad]) * pad:
            return None
        pt = pt[:-pad]
        head = pt[:200].lower()
        if b"trophy" not in head:
            return None
        if sum(1 for b in pt if 32 <= b < 127 or b in (9, 10, 13)) < len(pt) * 0.7:
            return None
        return pt
    except Exception:
        return None


def bruteforce_npid(blob, start=0, end=100000):
    """Find NPWRxxxxx_00 for an ESFM blob -> (npid, xml) or (None, None)."""
    try:
        from cryptography.hazmat.primitives.ciphers import (
            Cipher as _Cipher, algorithms as _Algos, modes as _Modes)
    except Exception:
        return None, None
    try:
        if not blob or len(blob) < 32:
            return None, None
        ct = blob[16:32]
        for i in range(start, end):
            npid = ("NPWR%05d_00" % i).encode().ljust(16, b"\x00")
            enc = _Cipher(_Algos.AES(TRP_TROPHY_KEY),
                          _Modes.CBC(bytes(16))).encryptor()
            ckey = enc.update(npid) + enc.finalize()
            dec = _Cipher(_Algos.AES(ckey),
                          _Modes.CBC(blob[:16])).decryptor()
            if (dec.update(ct) + dec.finalize())[:1] != b"<":
                continue
            xml = decrypt_esfm(blob, npid.rstrip(b"\x00").decode())
            if xml:
                return npid.rstrip(b"\x00").decode(), xml
        return None, None
    except Exception:
        return None, None


def parse_trophy_xml(xml):
    """TROP.SFM XML -> [{id, name, detail, type, hidden}]. Never raises."""
    try:
        import xml.etree.ElementTree as _ET
        root = _ET.fromstring(xml)
        out = []
        for t in root.iter("trophy"):
            try:
                out.append({"id": t.get("id", "?"),
                            "name": (t.findtext("name") or "").strip(),
                            "detail": (t.findtext("detail") or "").strip(),
                            "type": (t.get("ttype") or "?").upper(),
                            "hidden": (t.get("hidden") or "").lower() == "yes"})
            except Exception:
                continue
        return out
    except Exception:
        return []


def carve_trp_icons(data):
    """Raw PNGs hidden in a TRP (trophy icons + title banners).

    Not in the entry table — carved by magic. Returns [{off, size, w, h}]
    with dims from IHDR (no image decode). Strict: drops anything odd.
    Trophy icons are 240x240 in trophy-id order; 320x176 ones are banners.
    """
    try:
        import struct as _st
        if not data or len(data) < 100:
            return []
        out = []
        _at = 0
        while True:
            _s = data.find(b"\x89PNG\r\n\x1a\n", _at)
            if _s < 0:
                break
            _at = _s + 1
            if _s + 33 > len(data):
                continue
            if data[_s + 12:_s + 16] != b"IHDR":
                continue
            _w, _h = _st.unpack_from(">2I", data, _s + 16)
            if _w <= 0 or _h <= 0 or _w > 2048 or _h > 2048:
                continue
            _en = data.find(b"IEND", _s) + 8
            if _en <= 8 or _en - _s > 10_000_000 or _en > len(data):
                continue
            out.append({"off": _s, "size": _en - _s, "w": _w, "h": _h})
            if len(out) > 2000:
                break
        return out
    except Exception:
        return []


def parse_ucp(data):
    """PS5 trophy00.ucp archive (newer dumps use this instead of .trp).

    64-byte big-endian records @0x40: u32 ?, u32 offset, u32 ?,
    u32 size, 16 reserved bytes, 32-byte null-padded name.
    Payload is raw (PNG icons + tropmeta_*.json), 16-byte aligned.
    Returns [{name, off, size}] or []. Never raises.
    """
    try:
        import struct as _st
        if not data or len(data) < 0x80 or data[:4] != b"\xb2(\xc6\n":
            return []
        out = []
        base = 0x40
        while base + 64 <= len(data):
            f0, off, f2, size = _st.unpack_from(">4I", data, base)
            nm = data[base + 32:base + 64].split(b"\x00")[0]
            if not nm:
                break  # padding / end of table
            try:
                name = nm.decode("ascii")
            except Exception:
                break  # binary = ran into payload
            if not name or off + size > len(data) or size <= 0:
                # tombstone/empty slot (e.g. zero-size icon0): keep name only
                if name and size == 0 and off == 0:
                    base += 64
                    continue
                break
            out.append({"name": name, "off": off, "size": size})
            base += 64
            if len(out) > 10000:
                break
        return out
    except Exception:
        return []


def ucp_trophies(data):
    """UCP bytes -> (npid, [{id, name, detail}], {icon_name: bytes}).

    Language pick: en-US -> en-GB -> first tropmeta_*.json.
    Never raises; ([], {}, None) on failure.
    """
    try:
        import json as _json
        files = parse_ucp(data)
        if not files:
            return None, [], {}
        blobs = {}
        for f in files:
            blobs[f["name"]] = data[f["off"]:f["off"] + f["size"]]
        metas = sorted(n for n in blobs if n.startswith("tropmeta_")
                       and n.endswith(".json"))
        pick = next((n for n in ("tropmeta_en-US.json", "tropmeta_en-GB.json")
                     if n in blobs), None) or (metas[0] if metas else None)
        npid, trs = None, []
        title = ""
        if pick:
            try:
                o = _json.loads(blobs[pick].decode("utf-8"))
                npid = o.get("trophyNpCommId")
                md = o.get("metadata") or {}
                try:
                    title = str((md.get("titleMetadata") or {}).get("name", "")
                                or "")
                except Exception:
                    title = ""
                for t in md.get("trophyMetadata", []):
                    trs.append({"id": str(t.get("id", "?")),
                                "name": str(t.get("name", "") or ""),
                                "detail": str(t.get("detail", "") or "")})
            except Exception:
                pass
        icons = {n: b for n, b in blobs.items()
                 if n.lower().endswith(".png") and b[:4] == b"\x89PNG"}
        return npid, title, trs, icons
    except Exception:
        return None, "", [], {}


_EXO_GRADES = {}


def _norm_name(s):
    """Lowercase ASCII-folded name for cross-source trophy matching."""
    try:
        import unicodedata as _ud
        s = _ud.normalize("NFKD", str(s or ""))
        s = "".join(c for c in s if not _ud.combining(c))
        return "".join(c for c in s.lower() if c.isalnum())
    except Exception:
        return str(s or "").lower()


def fetch_exophase_grades(title):
    """{normname: P/G/S/B} from Exophase trophy list. {} on any failure.

    Slug is derived from the game title (ghost-of-yotei-psn); names are
    matched ASCII-folded. Cached per session. Never raises.
    Exophase blocks plain-URL clients (403), so browser headers are sent.
    """
    import re as _re
    import urllib.request as _ureq
    if not title or not str(title).strip():
        return {}
    key = _norm_name(title)
    if key in _EXO_GRADES:
        return _EXO_GRADES[key]
    if not _host_up("www.exophase.com"):
        return {}
    out = {}
    try:
        # fold diacritics but KEEP word separators for the slug
        import unicodedata as _ud
        _fold = "".join(
            c for c in _ud.normalize("NFKD", str(title))
            if not _ud.combining(c)).lower()
        slug = _re.sub(r"[^a-z0-9]+", "-", _fold).strip("-")
        if not slug:
            return out
        for cand in (slug + "-psn", slug + "-ps5", slug):
            url = "https://www.exophase.com/game/%s/trophies/" % cand
            try:
                req = _ureq.Request(url, headers=_BROWSER_HEADERS)
                with _ureq.urlopen(req, timeout=8) as r:
                    html = r.read().decode("utf-8", "replace")
            except Exception:
                continue
            titles = _re.findall(
                r'fw-bolder">\s*<a[^>]*>([^<]+)</a>', html)
            grades = _re.findall(
                r'exo-icon-trophy-(platinum|gold|silver|bronze)', html)
            if not titles or len(titles) != len(grades):
                continue
            _gm = {"platinum": "P", "gold": "G",
                   "silver": "S", "bronze": "B"}
            for n, g in zip(titles, grades):
                out[_norm_name(n)] = _gm[g]
            if out:
                break
            out = {}
    except Exception:
        out = {}
    _EXO_GRADES[key] = out
    return out


def _ucp_ring(png):
    """Classify a UCP trophy icon ring: gold/gray/copper/''.

    Ring art differs per game (Ghost bronze=copper, Astro bronze=gray),
    so this returns the raw color class; the caller maps the majority
    class to Bronze. Never raises.
    """
    try:
        import colorsys as _cs
        import math as _math
        import statistics as _st
        from PIL import Image as _Img
        import io as _io
        im = _Img.open(_io.BytesIO(png)).convert("RGB")
        w, h = im.size
        if w < 64 or h < 64:
            return ""
        cx, cy = w / 2, h / 2
        px = im.load()
        best_sat = (0, 0, 0)   # (sat, hue, val)
        best_gray = 0          # brightest low-sat ring radius value
        rr = 0.30
        while rr <= 0.485:
            ss, hs, vs = [], [], []
            a = 0
            while a < 360:
                x = int(cx + rr * w * _math.cos(_math.radians(a)))
                y = int(cy + rr * w * _math.sin(_math.radians(a)))
                try:
                    R, G, B = px[x, y]
                except IndexError:
                    a += 15
                    continue
                H, S, V = _cs.rgb_to_hsv(R / 255, G / 255, B / 255)
                hs.append(H * 360)
                ss.append(S)
                vs.append(V)
                a += 15
            if ss:
                ms, mh, mv = _st.median(ss), _st.median(hs), _st.median(vs)
                if ms > best_sat[0]:
                    best_sat = (ms, mh, mv)
                if ms < 0.25 and mv > best_gray:
                    best_gray = mv
            rr += 0.02
        ms, mh, mv = best_sat
        if ms > 0.30 and 32 <= mh <= 55:
            return "gold"
        if best_gray > 0.45:
            return "gray"
        if ms > 0.30 and (mh <= 25 or mh >= 340):
            return "copper"
        return ""
    except Exception:
        return ""


def _ucp_grade(png, tid, detail):
    """Legacy single-icon guess (kept for compatibility)."""
    ring = _ucp_ring(png) if png else ""
    if str(tid or "").strip() in ("0000", "0"):
        return "P"
    return {"gold": "G", "gray": "S", "copper": "B"}.get(ring, "")


def read_entry_bytes(path, abs_off, size, limit=32_000_000):
    if isinstance(abs_off, tuple) and abs_off and abs_off[0] == "ps3":
        _, retail, keymat, doff, fo = abs_off
        if size <= 0 or size > limit:
            return b""
        with open(path, "rb") as f:
            return _ps3_decrypt(f, doff, retail, keymat, fo, size)
    if isinstance(abs_off, tuple) and abs_off and abs_off[0] == "exfat":
        _, first, fsize, nofat = abs_off
        if fsize <= 0 or fsize > limit:
            return b""
        fs = _Exfat(path)
        try:
            if nofat:
                fs.f.seek(fs._clus_off(first))
                return fs.f.read(fsize)
            return fs.read_chain(first, fsize)
        finally:
            fs.close()
    if isinstance(abs_off, int) and abs_off < 0:
        return b""
    if size <= 0 or size > limit:
        return b""
    with open(path, "rb") as f:
        f.seek(abs_off)
        return f.read(size)


def fmt_size(n):
    if n >= 1e9:
        return f"{n / 1e9:.2f} GB"
    if n >= 1e6:
        return f"{n / 1e6:.1f} MB"
    if n >= 1e3:
        return f"{n / 1e3:.1f} KB"
    return f"{n} B"


CURATED_SFO = ["TITLE", "TITLE_ID", "CATEGORY", "VERSION", "CONTENT_ID", "FORMAT"]
# (key in param.json, friendly label shown in Details; None = decode via fmt_fw)
CURATED_JSON = [("titleId", "Title ID"),
                ("contentId", "Content ID"),
                ("contentVersion", "Content Version"),
                ("masterVersion", "Master Version"),
                ("conceptId", "Concept ID"),
                ("applicationDrmType", "DRM"),
                ("requiredSystemSoftwareVersion", "Min. System"),
                ("sdkVersion", "SDK")]


def friendly_json_value(key, v):
    if key in ("sdkVersion", "requiredSystemSoftwareVersion"):
        return fmt_fw(v)
    if isinstance(v, int):
        return str(v)
    return str(v)


def curated_meta_lines(kind, meta):
    """Short useful subset of param.sfo / param.json."""
    lines = []
    if not isinstance(meta, dict):
        return lines
    if kind == "ps5":
        lp = meta.get("localizedParameters", {}) or {}
        lang = lp.get("defaultLanguage", "en-US")
        t = (lp.get(lang) or {}).get("titleName", "")
        if t:
            lines.append(f"Title = {t}")
        for k, label in CURATED_JSON:
            if k in meta:
                lines.append(f"{label} = {friendly_json_value(k, meta[k])}")
    else:
        # Show less: short useful subset in fixed order (Show all = full table).
        order = ["TITLE", "TITLE_ID", "CATEGORY", "CONTENT_ID",
                 "VERSION", "APP_VER", "SYSTEM_VER", "FORMAT",
                 "PARENTAL_LEVEL"]
        titles = sorted(k for k in meta
                        if k.startswith("TITLE_") and k[6:].isdigit())
        collapsed = False
        if len(titles) > 1:
            groups = {}
            for k in titles:
                groups.setdefault(str(meta[k]), []).append(k)
            if len(groups) < len(titles):
                collapsed = True
                for val, ks in sorted(groups.items(),
                                      key=lambda kv: kv[1][0]):
                    ks = sorted(ks)
                    if len(ks) == 1:
                        lines.append(f"{ks[0]} = {val}")
                    else:
                        lines.append(f"{ks[0]}..{ks[-1]} "
                                     f"({len(ks)} langs) = {val}")
        for k in order:
            if k not in meta:
                continue
            if k == "TITLE" and collapsed:
                continue  # localized titles already shown above
            v = meta[k]
            if isinstance(v, str) and not v.strip():
                continue
            lines.append(f"{k} = {v}")
    return lines


def full_meta_lines(meta):
    lines = []
    if isinstance(meta, dict):
        for k in sorted(meta.keys()):
            if k.startswith("_"):
                continue
            v = meta[k]
            if isinstance(v, dict):
                v = json.dumps(v, ensure_ascii=False)[:300]
            lines.append(f"{k} = {str(v)[:200]}")
    return lines


def sanitize_filename_part(s, limit=120):
    """Make a string safe for a Windows file/folder name. Never raises."""
    try:
        s = str(s or "")
    except Exception:
        return ""
    s = "".join(ch if ch not in '<>:"/\\|?*' and ord(ch) >= 32 else " " for ch in s)
    s = " ".join(s.split())
    s = s.strip(" .")
    if len(s) > limit:
        s = s[:limit].rstrip(" .")
    return s


REGION_SHORT = {"Europe": "EU", "Americas": "US", "Japan": "JP", "Asia": "AS"}


def normalize_version(ver):
    """Clean version for filenames: '04.040.100' -> '4.40.100'.

    First segment always unpadded; other segments only unpadded when
    longer than 2 chars (keeps conventional '1.06' / '1.00'). Never raises.
    """
    try:
        segs = str(ver).strip().split(".")
        out = []
        for i, s in enumerate(segs):
            s = s.strip()
            if s.isdigit() and (i == 0 or len(s) > 2):
                s = str(int(s))
            if s != "":
                out.append(s)
        return ".".join(out)
    except Exception:
        try:
            return str(ver).strip()
        except Exception:
            return ""


NAME_PARTS = (("title", "Title"), ("tid", "Title ID"),
               ("ver", "Version"), ("region", "Region"))


def build_clean_name(result, parts=None):
    """Clean uniform file/folder base name from parsed PKG info.

    Format: Title - TID - vVersion - Region (empty parts dropped).
    parts: optional {title, tid, ver, region} bools to pick components
    (rename dialog ticks). All on by default.
    Returns "" if neither Title ID nor title is available.
    """
    _pon = {"title": True, "tid": True, "ver": True, "region": True}
    if parts:
        try:
            _pon.update(parts)
        except Exception:
            pass
    try:
        rd = dict(result.get("rows") or [])
    except Exception:
        rd = {}
    try:
        title = str(result.get("title") or "").strip()
    except Exception:
        title = ""
    tid = str(rd.get("Title ID", "") or "").strip()
    ver = str(rd.get("Version", "") or rd.get("Content Ver", "") or "").strip()
    if ver[:1].lower() == "v":
        ver = ver[1:]
    ver = normalize_version(ver)
    region = str(rd.get("Region", "") or "").strip()
    region = REGION_SHORT.get(region, region)
    out = []
    if title and _pon.get("title"):
        out.append(title)
    if tid and tid != title and _pon.get("tid"):
        out.append(tid)
    if ver and ver != "-" and _pon.get("ver"):
        out.append("v" + ver)
    if region and region != "-" and _pon.get("region"):
        out.append(region)
    # non-base packages (Update/DLC) get a suffix so base+update of the
    # same version don't collide on one name (e.g. Crysis 2 v1.01 twice)
    _ptype = str(rd.get("Type", "") or "").strip()
    if _ptype.lower() in ("update", "dlc"):
        out.append(_ptype)
    if not out:
        return ""
    return sanitize_filename_part(" - ".join(out))


BATCH_EXTS = (".pkg", ".ffpkg", ".ffpfsc", ".exfat")


def split_set_siblings(path):
    """All parts of a split set (game_0.pkg, game_1.pkg, ...) or [path].

    Only .pkg uses the _N convention. Never raises.
    """
    import re as _re
    try:
        d = os.path.dirname(path)
        base = os.path.basename(path)
        if not base.lower().endswith(".pkg"):
            return [path]
        m = _re.search(r"^(.*)_(\d+)\.pkg$", base, _re.IGNORECASE)
        if not m:
            return [path]
        import glob as _glob
        sibs = sorted(_glob.glob(os.path.join(d, m.group(1) + "_*.pkg")))
        sibs = [p for p in sibs if _re.search(r"_\d+\.pkg$", p, _re.IGNORECASE)]
        sibs.sort(key=lambda p: int(
            _re.search(r"_(\d+)\.pkg$", p, _re.IGNORECASE).group(1)))
        if len(sibs) > 1 and any(
                os.path.normcase(p) == os.path.normcase(path) for p in sibs):
            return sibs
    except Exception:
        pass
    return [path]


def collect_batch_files(inputs, recursive=False):
    """Expand files/folders into a deduped file list (batch extensions only)."""
    seen, out = set(), []
    for inp in inputs or []:
        try:
            if os.path.isdir(inp):
                if recursive:
                    for _dp, _dn, fns in os.walk(inp):
                        for fn in fns:
                            _fp = os.path.join(_dp, fn)
                            _k = os.path.normcase(os.path.abspath(_fp))
                            if _fp.lower().endswith(BATCH_EXTS) and _k not in seen:
                                seen.add(_k)
                                out.append(_fp)
                else:
                    for fn in sorted(os.listdir(inp)):
                        _fp = os.path.join(inp, fn)
                        _k = os.path.normcase(os.path.abspath(_fp))
                        if os.path.isfile(_fp) and _fp.lower().endswith(BATCH_EXTS) \
                                and _k not in seen:
                            seen.add(_k)
                            out.append(_fp)
            elif os.path.isfile(inp):
                _k = os.path.normcase(os.path.abspath(inp))
                if _k not in seen:
                    seen.add(_k)
                    out.append(inp)
        except Exception:
            continue
    return out


def preview_batch(files, include=None):
    """Build a rename plan for files. Split sets stay together (one entry).

    Each item: {files, new_files, new_base, status, reason}.
    status: 'ok' | 'skip'. Never renames anything.
    include: optional name-component ticks, passed to build_clean_name.
    """
    import re as _re
    plan, seen_sets, seen_targets = [], set(), set()
    for fp in files or []:
        try:
            parts = split_set_siblings(fp)
        except Exception:
            parts = [fp]
        setkey = os.path.normcase(os.path.abspath(parts[0]))
        if setkey in seen_sets:
            continue
        seen_sets.add(setkey)
        item = {"files": parts, "new_files": [],
                "new_base": "", "status": "skip", "reason": ""}
        try:
            r = parse_pkg(parts[0])
        except Exception as e:
            item["reason"] = f"parse error: {e}"
            plan.append(item)
            continue
        if not r.get("ok"):
            item["reason"] = r.get("error", "unrecognized file")
            plan.append(item)
            continue
        base = build_clean_name(r, parts=include)
        if not base:
            item["reason"] = "not enough info for a name"
            plan.append(item)
            continue
        item["new_base"] = base
        d = os.path.dirname(parts[0])
        if len(parts) == 1:
            _root, ext = os.path.splitext(os.path.basename(parts[0]))
            item["new_files"] = [os.path.join(d, base + ext)]
        else:
            for p in parts:
                m = _re.search(r"_(\d+)(\.[^.]+)$", os.path.basename(p))
                num, ext = (m.group(1), m.group(2)) if m else ("0", ".pkg")
                item["new_files"] = item.get("new_files", []) + \
                    [os.path.join(d, f"{base}_{num}{ext}")]
        problems = []
        for old, new in zip(item["files"], item["new_files"]):
            if os.path.normcase(old) == os.path.normcase(new):
                continue
            _nk = os.path.normcase(os.path.abspath(new))
            if os.path.exists(new):
                problems.append(f"target exists: {os.path.basename(new)}")
            elif _nk in seen_targets:
                problems.append(f"duplicate target: {os.path.basename(new)}")
        if problems:
            item["reason"] = "; ".join(problems)
            plan.append(item)
            continue
        for new in item["new_files"]:
            seen_targets.add(os.path.normcase(os.path.abspath(new)))
        if all(os.path.normcase(o) == os.path.normcase(n)
               for o, n in zip(item["files"], item["new_files"])):
            item["reason"] = "name unchanged"
            plan.append(item)
            continue
        item["status"] = "ok"
        plan.append(item)
    return plan


def apply_batch(plan, log_path=None, only_ok=True):
    """Execute a preview_batch plan. Returns (renamed, skipped, log_path).

    renamed: [(old, new)], skipped: [(old, reason)]. Writes a revert log.
    """
    import datetime as _dt
    renamed, skipped = [], []
    lines = [f"# PKGViewer batch rename {_dt.datetime.now():%Y-%m-%d %H:%M:%S}"]
    for item in plan or []:
        if item.get("status") != "ok" and only_ok:
            for f in item.get("files", []):
                skipped.append((f, item.get("reason", "skipped")))
            continue
        if item.get("status") != "ok":
            continue
        for old, new in zip(item["files"], item["new_files"]):
            if os.path.normcase(old) == os.path.normcase(new):
                continue
            if os.path.exists(new):
                skipped.append((old, f"target exists: {os.path.basename(new)}"))
                continue
            try:
                os.rename(old, new)
            except Exception as e:
                skipped.append((old, str(e)))
                continue
            renamed.append((old, new))
            lines.append(f"{old}\t{new}")
    lp = None
    if log_path and renamed:
        try:
            with open(log_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            lp = log_path
        except Exception:
            lp = None
    return renamed, skipped, lp


def default_batch_log():
    import datetime as _dt
    return os.path.abspath(
        f"batch_rename_{_dt.datetime.now():%Y%m%d_%H%M%S}.log")


def parse_revert_log(path):
    """Read a batch_rename_*.log file. Returns [(current, restore)].

    Each log line is "old\\trestore-target". Revert walks it backwards:
    current = the name after renaming, restore = the original name.
    Comment (#) and malformed lines are skipped. Never raises.
    """
    pairs = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) != 2:
                    continue
                old, new = parts[0].strip(), parts[1].strip()
                if not old or not new:
                    continue
                pairs.append((new, old))
    except Exception:
        return []
    return pairs


def apply_revert(pairs, only_existing=True):
    """Rename current names back to originals. Returns (reverted, skipped).

    reverted: [(current, restore)], skipped: [(current, reason)].
    Never raises.
    """
    reverted, skipped = [], []
    for current, restore in pairs or []:
        if os.path.normcase(current) == os.path.normcase(restore):
            continue
        if only_existing and not os.path.exists(current):
            skipped.append((current, "current file not found"))
            continue
        if os.path.exists(restore):
            skipped.append((current,
                            f"target exists: {os.path.basename(restore)}"))
            continue
        try:
            os.rename(current, restore)
        except Exception as e:
            skipped.append((current, str(e)))
            continue
        reverted.append((current, restore))
    return reverted, skipped


def print_batch(inputs, recursive=False, apply=False):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    files = collect_batch_files(inputs, recursive=recursive)
    if not files:
        print("No game files found.")
        return
    plan = preview_batch(files)
    n_ok = sum(1 for i in plan if i["status"] == "ok")
    for item in plan:
        if item["new_files"]:
            for old, new in zip(item["files"], item["new_files"]):
                tag = "OK  " if item["status"] == "ok" else "SKIP"
                extra = "" if item["status"] == "ok" \
                    else f"  ({item['reason']})"
                print(f"[{tag}] {os.path.basename(old)}  ->  "
                      f"{os.path.basename(new)}{extra}")
        else:
            print(f"[SKIP] {os.path.basename(item['files'][0])}  "
                  f"({item['reason']})")
    print(f"--- {n_ok} of {len(plan)} ready ---")
    if not apply:
        print("Dry run. Re-run with --apply to rename.")
        return
    log = default_batch_log()
    renamed, skipped, lp = apply_batch(plan, log_path=log)
    print(f"Renamed {len(renamed)}, skipped {len(skipped)}."
          + (f" Log: {lp}" if lp else ""))


def copy_image_to_clipboard(pil_img):
    """Copy PIL image to Windows clipboard as DIB (ctypes only). None = ok."""
    try:
        from PIL import Image as _I
        import ctypes
        from ctypes import wintypes
        import io as _io
        img = pil_img if pil_img.mode in ("RGB", "RGBA") else pil_img.convert("RGB")
        if img.mode == "RGBA":
            bg = _I.new("RGB", img.size, (255, 255, 255))
            bg.paste(img, mask=img.split()[3])
            img = bg
        buf = _io.BytesIO()
        img.save(buf, "BMP")
        dib = buf.getvalue()[14:]
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = wintypes.BOOL
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.restype = ctypes.c_void_p
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = wintypes.BOOL
        user32.EmptyClipboard.restype = wintypes.BOOL
        user32.SetClipboardData.argtypes = [wintypes.UINT, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.restype = wintypes.BOOL
        h = kernel32.GlobalAlloc(0x0002, len(dib))
        if not h:
            return "GlobalAlloc failed"
        p = kernel32.GlobalLock(h)
        if not p:
            kernel32.GlobalFree(h)
            return "GlobalLock failed"
        ctypes.memmove(p, dib, len(dib))
        kernel32.GlobalUnlock(h)
        if not user32.OpenClipboard(None):
            kernel32.GlobalFree(h)
            return "OpenClipboard failed"
        user32.EmptyClipboard()
        if not user32.SetClipboardData(8, h):
            user32.CloseClipboard()
            kernel32.GlobalFree(h)
            return "SetClipboardData failed"
        user32.CloseClipboard()
        return None
    except Exception as e:
        return str(e)


def print_info(path):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    r = parse_pkg(path)
    if "error" in r and not r.get("ok"):
        print("ERROR:", r["error"]); return
    print("FILE:", os.path.basename(path))
    print("TITLE:", r["title"])
    for k, v in r["rows"]:
        print(f"{k}: {v}")
    print(f"--- entries ({len(r['entries'])}) ---")
    for e in r["entries"]:
        _cd = e.get("codec")
        _tag = f" [{_cd}]" if _cd and _cd != "-" else ""
        print(f"  id={e['id']} size={e['size']} name={e['name']!r}{_tag}")
    for _al in r.get("ampr_lines", []):
        print(f"  AMPR: {_al}")


# ---------------- GUI ----------------
BG, CARD, CARD2, ACCENT = "#171717", "#202020", "#2a2a2a", "#4f8ef7"
TEXT, MUTED = "#f1f3f8", "#8b93a5"
FONT = ("Segoe UI", 10)
FONT_BIG = ("Segoe UI", 18, "bold")
FONT_MID = ("Segoe UI", 11, "bold")
FONT_SMALL = ("Segoe UI", 9)
FONT_BADGE = ("Segoe UI", 9, "bold")


def _global_ctrl_keys(event, root, statusvar):
    """Layout-independent Ctrl+A / Ctrl+C (uses keycode, not keysym).
    Works with Persian/Arabic layouts where keysym differs."""
    import tkinter as tk
    if not (event.state & 0x4):
        return None
    kc = event.keycode
    ks = (event.keysym or "").lower()
    is_a = (kc == 65 or ks == "a")
    is_c = (kc == 67 or ks == "c")
    if not (is_a or is_c):
        return None
    try:
        w = root.focus_get()
    except Exception:
        return None
    try:
        if isinstance(w, tk.Text):
            if is_a:
                w.tag_add("sel", "1.0", "end-1c")
                w.mark_set("insert", "end-1c")
                w.see("insert")
                return "break"
            try:
                sel = w.get("sel.first", "sel.last")
            except Exception:
                return None
            w.clipboard_clear()
            w.clipboard_append(sel)
            try:
                w.update()
            except Exception:
                pass
            statusvar.set("Text copied")
            return "break"
        elif isinstance(w, tk.Entry):
            if is_a:
                w.select_range(0, "end")
                return "break"
            if not w.selection_present():
                return None
            sel = w.selection_get()
            w.clipboard_clear()
            w.clipboard_append(sel)
            try:
                w.update()
            except Exception:
                pass
            statusvar.set("Text copied")
            return "break"
    except Exception:
        return None
    return None


def _local_logo(size=(40, 40)):
    """Load local assets/logo.png if present (gitignored, never committed)."""
    try:
        from PIL import Image as _I
        here = os.path.dirname(os.path.abspath(__file__))
        cands = [os.path.join(os.getcwd(), "assets", "logo.png"),
                 os.path.join(here, "assets", "logo.png")]
        if getattr(sys, "frozen", False):
            cands.insert(0, os.path.join(os.path.dirname(sys.executable),
                                         "assets", "logo.png"))
            cands.insert(0, os.path.join(sys._MEIPASS, "assets", "logo.png"))
        for p in cands:
            if os.path.isfile(p):
                im = _I.open(p).convert("RGBA")
                im.thumbnail(size, _I.LANCZOS)
                return im
        return None
    except Exception:
        return None


def _format_icon_image(name, size=(28, 28)):
    """Load assets/icons/<name>.ico (pkg/exfat/ffpfsc/ffpkg) for in-app badge."""
    try:
        from PIL import Image as _I
        here = os.path.dirname(os.path.abspath(__file__))
        cands = [os.path.join(os.getcwd(), "assets", "icons", name + ".ico"),
                 os.path.join(here, "assets", "icons", name + ".ico")]
        if getattr(sys, "frozen", False):
            cands.insert(0, os.path.join(sys._MEIPASS, "assets", "icons", name + ".ico"))
            cands.insert(0, os.path.join(os.path.dirname(sys.executable),
                                         "assets", "icons", name + ".ico"))
        for p in cands:
            if os.path.isfile(p):
                im = _I.open(p).convert("RGBA")
                im.thumbnail(size, _I.LANCZOS)
                return im
        return None
    except Exception:
        return None


def run_gui(start_path=None):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    try:
        from PIL import Image, ImageTk
        has_pil = True
    except ImportError:
        has_pil = False

    state = {"result": None, "photo": None, "pil": None,
             "img_name": "", "show_all": False}

    root = None
    has_dnd = False
    try:
        from tkinterdnd2 import DND_FILES, TkinterDnD
        root = TkinterDnD.Tk()
        has_dnd = True
    except ImportError:
        root = tk.Tk()
    try:
        # hide until layout is applied:
        # avoids white flash + resize jump on startup
        root.withdraw()
    except Exception:
        pass
    root.title("PKG Viewer %s  •  PS3 / PS4 / PS5  •  by Loopayeh" % APP_VERSION)
    root.geometry("880x450")
    root.configure(bg=BG)
    root.minsize(880, 450)
    try:
        _ic = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(sys.executable)
                            if getattr(sys, "frozen", False) else "."), "assets", "logo.ico")
        if os.path.isfile(_ic):
            root.iconbitmap(_ic)
    except Exception:
        pass

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("Card2.TFrame", background=CARD2)
    style.configure("TLabel", background=BG, foreground=TEXT, font=FONT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=FONT)
    style.configure("Muted.Card.TLabel", background=CARD, foreground=MUTED, font=FONT_SMALL)
    style.configure("Title.Card.TLabel", background=CARD, foreground=TEXT, font=FONT_BIG)
    style.configure("Badge.TLabel", background=CARD2, foreground=TEXT, font=FONT_BADGE,
                    padding=(10, 4))
    style.configure("SpecKey.TLabel", background=CARD, foreground=MUTED, font=FONT_SMALL)
    style.configure("SpecVal.TLabel", background=CARD, foreground=TEXT, font=FONT_MID)
    style.configure("Accent.TButton", background=ACCENT, foreground="#171717", font=FONT,
                    borderwidth=0, padding=(16, 9))
    style.map("Accent.TButton", background=[("active", "#6fa8ff")])
    style.configure("TNotebook", background=BG, borderwidth=0,
                    lightcolor=BG, darkcolor=BG, bordercolor=BG)
    style.configure("TNotebook.Tab", background=CARD, foreground=MUTED, padding=(18, 8), font=FONT,
                    borderwidth=0, lightcolor=CARD, darkcolor=CARD, bordercolor=CARD)
    style.map("TNotebook.Tab", background=[("selected", CARD2)],
              foreground=[("selected", TEXT)],
              lightcolor=[("selected", CARD2)], darkcolor=[("selected", CARD2)])
    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                    font=FONT, rowheight=26, borderwidth=0, relief="flat",
                    lightcolor=CARD, darkcolor=CARD, bordercolor=CARD)
    style.configure("Treeview.Heading", background=CARD2, foreground=MUTED, font=FONT_SMALL,
                    relief="flat", borderwidth=0,
                    lightcolor=CARD2, darkcolor=CARD2)
    style.map("Treeview.Heading", background=[("active", CARD2)])
    style.map("Treeview", background=[("selected", ACCENT)])
    style.configure("Vertical.TScrollbar", background=CARD2, troughcolor=BG,
                    bordercolor=BG, lightcolor=CARD2, darkcolor=CARD2,
                    arrowcolor=MUTED, relief="flat", borderwidth=0,
                    arrowsize=13)
    style.map("Vertical.TScrollbar", background=[("active", "#3b70c9")],
              arrowcolor=[("active", TEXT)])
    style.configure("TCombobox", fieldbackground=CARD2, background=CARD2, foreground=TEXT,
                    arrowcolor=MUTED)
    style.map("TCombobox",
              fieldbackground=[("readonly", CARD2), ("disabled", CARD2)],
              foreground=[("readonly", TEXT), ("disabled", MUTED)],
              background=[("readonly", CARD2)],
              arrowcolor=[("disabled", MUTED)],
              selectbackground=[("readonly", ACCENT)],
              selectforeground=[("readonly", "#171717")])
    root.option_add("*TCombobox*Listbox.background", CARD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
    root.option_add("*TCombobox*Listbox.selectForeground", "#171717")
    root.option_add("*TCombobox*Entry.background", CARD2)
    root.option_add("*TCombobox*Entry.foreground", TEXT)
    root.option_add("*TCombobox*Entry.readonlybackground", CARD2)
    root.option_add("*TCombobox*Entry.selectBackground", ACCENT)
    root.option_add("*TCombobox*Entry.selectForeground", "#171717")
    root.option_add("*TCombobox*Entry.insertBackground", TEXT)
    style.configure("Ghost.TButton", background="#404040", foreground=TEXT, font=FONT,
                    borderwidth=0, padding=(12, 7))
    style.map("Ghost.TButton", background=[("active", "#2c3342")])

    # header: slim toolbar (About/updates live at bottom-right now)
    header = ttk.Frame(root, padding=(10, 4))
    header.pack(fill="x")
    try:
        _lg = _local_logo((36, 36))
        if _lg is not None:
            from PIL import ImageTk as _ITk
            _lph = _ITk.PhotoImage(_lg)
            state["logo_photo"] = _lph
            tk.Label(header, image=_lph, bg=BG).pack(side="left", padx=(0, 12))
    except Exception:
        pass
    mkbtn(header, text="Open", style="Accent.TButton",
               command=lambda: pick()).pack(side="left")
    renamebtn = mkbtn(header, text="Rename", style="Ghost.TButton",
                      command=lambda: show_rename())
    renamebtn.pack(side="left", padx=(8, 0))
    try:
        renamebtn.config(state="disabled")
    except Exception:
        pass
    batchbtn = mkbtn(header, text="Batch", style="Ghost.TButton",
                     command=lambda: pick_many())
    batchbtn.pack(side="left", padx=(8, 0))
    undobtn = mkbtn(header, text="Undo", style="Ghost.TButton",
                    command=lambda: undo_last_rename())
    undobtn.pack(side="left", padx=(8, 0))
    try:
        undobtn.config(state="disabled")
    except Exception:
        pass
    def toggle_pin(force=None):
        # always-on-top toggle (Pin button, header right)
        try:
            cur = bool(root.attributes("-topmost"))
        except Exception:
            cur = False
        on = (not cur) if force is None else bool(force)
        try:
            root.attributes("-topmost", on)
        except Exception:
            return
        state["pinned"] = on
        try:
            pinbtn.config(text="Pinned" if on else "Pin")
        except Exception:
            pass
        try:
            _save_settings({"pinned": on})
        except Exception:
            pass
    pinbtn = mkbtn(header, text="Pin", style="Ghost.TButton",
                   command=lambda: toggle_pin())
    pinbtn.pack(side="right", padx=(0, 8))
    state["pinbtn"] = pinbtn
    def toggle_cover(force=None):
        # coverless mode: hide the whole left column (cover + title +
        # format) and shrink the window down to the right column, so no
        # empty space is left behind. Saved.
        try:
            hidden = bool(state.get("cover_hidden"))
        except Exception:
            hidden = False
        hide = (not hidden) if force is None else bool(force)
        try:
            if hide:
                try:
                    _cw, _ch = root.winfo_width(), root.winfo_height()
                    if _cw > 100 and _ch > 100:
                        state["cover_saved_geo"] = (_cw, _ch)
                except Exception:
                    pass
                left.grid_remove()
                # file path drops to a wrapped row under the buttons
                try:
                    _pl = state.get("pathlabel")
                    _sh = state.get("subheader")
                    if _pl is not None:
                        _pl.pack_forget()
                    if _sh is not None:
                        _sh.pack(fill="x", padx=12, pady=(0, 4), before=body)
                except Exception:
                    pass
                try:
                    if root.winfo_viewable():
                        # shrink-wrap like the old compact mode: the right
                        # column fills, so req alone never shrinks — cap it
                        root.update_idletasks()
                        _w = min(max(root.winfo_reqwidth(), 360), 620)
                        _h = min(max(root.winfo_reqheight(), 280), 430)
                        root.geometry("%dx%d" % (_w, _h))
                        root.minsize(_w, _h)
                except Exception:
                    pass
            else:
                left.grid()
                # file path back into the header button row
                try:
                    _pl = state.get("pathlabel")
                    _sh = state.get("subheader")
                    if _sh is not None:
                        _sh.pack_forget()
                    if _pl is not None:
                        _pl.pack(side="left", padx=(14, 0))
                except Exception:
                    pass
                try:
                    if root.winfo_viewable():
                        root.update_idletasks()
                        _sg = state.get("cover_saved_geo")
                        if _sg and _sg[0] > 100 and _sg[1] > 100:
                            root.geometry("%dx%d" % _sg)
                            root.minsize(_sg[0], _sg[1])
                        else:
                            root.geometry("880x450")
                            root.minsize(880, 450)
                except Exception:
                    pass
        except Exception:
            return
        state["cover_hidden"] = hide
        try:
            coverbtn.config(text="Show cover" if hide else "Hide cover")
        except Exception:
            pass
        try:
            _save_settings({"cover_hidden": hide})
        except Exception:
            pass
    coverbtn = mkbtn(header, text="Hide cover", style="Ghost.TButton",
                     command=lambda: toggle_cover())
    coverbtn.pack(side="right", padx=(0, 8))
    state["coverbtn"] = coverbtn
    pathvar = tk.StringVar(value="Drop a .pkg / .exfat / .ffpfsc / .ffpkg file or app folder here")
    pathlabel = ttk.Label(header, textvariable=pathvar, font=FONT_SMALL, foreground=MUTED)
    pathlabel.pack(side="left", padx=(14, 0))
    state["pathlabel"] = pathlabel
    # second header row for coverless mode: the file path moves down
    # here (wrapped) instead of being clipped in the narrow window.
    # (Tk can't reparent a widget, so two labels share one textvar.)
    subheader = ttk.Frame(root)
    state["subheader"] = subheader
    subpathlabel = ttk.Label(subheader, textvariable=pathvar,
                             font=FONT_SMALL, foreground=MUTED,
                             wraplength=590, justify="left")
    subpathlabel.pack(anchor="w", fill="x")

    # bottom bar FIRST (packed before body) so it stays pinned at the
    # bottom no matter how small the window gets
    bottombar = ttk.Frame(root)
    bottombar.pack(fill="x", side="bottom")
    statusvar = tk.StringVar(value="Ready")
    _status_lbl = tk.Label(bottombar, textvariable=statusvar, bg=BG, fg=MUTED,
                           font=FONT_SMALL, anchor="w", justify="left",
                           padx=12, pady=6)
    _status_lbl.pack(side="left", fill="x", expand=True)
    # small About / updates buttons, bottom-right (PKG Sender style)
    updatebtn = mkbtn(bottombar, text="Check updates", style="Ghost.TButton",
                      bg=BG, font=(FONT[0], 8),
                      command=lambda: check_updates(manual=True))
    updatebtn.pack(side="right", padx=(0, 8), pady=2)
    mkbtn(bottombar, text="About", style="Ghost.TButton", bg=BG,
          font=(FONT[0], 8),
          command=lambda: show_about()).pack(side="right", padx=(0, 4), pady=2)
    # wrap status text on narrow windows instead of clipping it
    bottombar.bind("<Configure>",
                   lambda e: _status_lbl.config(wraplength=max(200, e.width - 24)))

    # body
    body = ttk.Frame(root, padding=(10, 2))
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)
    body.rowconfigure(0, weight=1)

    # ---- hero: cover + title/badges (left) ----
    left = ttk.Frame(body, style="Card.TFrame", padding=8)
    left.grid(row=0, column=0, sticky="ns", padx=(0, 10))
    imgframe = tk.Frame(left, bg=CARD, width=280, height=280)
    imgframe.pack(pady=(6, 0))
    imgframe.pack_propagate(False)
    state["imgframe"] = imgframe
    imglabel = tk.Label(imgframe, bg=CARD, fg=MUTED,
                        text="Drop a file or folder here\n\nor click Open",
                        font=FONT_MID, justify="center")
    imglabel.place(relx=0.5, rely=0.5, anchor="center")
    titlevar = tk.StringVar(value="—")
    titlerow = tk.Frame(left, bg=CARD)
    titlerow.pack(pady=(6, 4), anchor="w", fill="x")
    state["titlerow"] = titlerow
    fmtlabel = tk.Label(titlerow, bg=CARD, fg=MUTED, text="")
    fmtlabel.pack(side="left", padx=(0, 8))
    state["fmtlabel"] = fmtlabel
    tk.Label(titlerow, textvariable=titlevar, bg=CARD, fg=TEXT, font=(FONT[0], 11, "bold"),
             wraplength=220, justify="left").pack(side="left", anchor="w")
    badgevars = [tk.StringVar(value="") for _ in range(5)]
    state["badges"] = badgevars
    state["badge_labels"] = []
    # image stepping helper (Images tab buttons use this)
    state["imgnames"] = []
    def _step_image(d):
        vals = list(state.get("imgnames") or [])
        if not vals:
            return
        try:
            i = vals.index(state.get("img_name"))
        except ValueError:
            i = 0
        i = (i + d) % len(vals)
        show_image(vals[i])

    # right column
    right = ttk.Frame(body)
    right.grid(row=0, column=1, sticky="nsew")
    right.rowconfigure(1, weight=1)
    right.columnconfigure(0, weight=1)

    state["spec_cells"] = []

    nb = ttk.Notebook(right)
    nb.pack(fill="both", expand=True)
    state["notebook"] = nb
    tab_entries = ttk.Frame(nb)
    tab_meta = ttk.Frame(nb)
    tab_specs = ttk.Frame(nb)
    nb.add(tab_specs, text="  Specs  ")
    nb.add(tab_meta, text="  Details  ")
    nb.add(tab_entries, text="  Files  ")
    # Specs tab: the classic 2-column grid (PACKAGE/SIGNATURE/...)
    # for whoever wants the fine details at a glance
    specbox = ttk.Frame(tab_specs, style="Card.TFrame", padding=8)
    specbox.pack(fill="x", pady=(0, 8))
    spec_rows = []
    for _ in range(5):
        row = ttk.Frame(specbox, style="Card.TFrame")
        row.pack(fill="x", pady=1)
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        cells = []
        for col in (0, 1):
            cell = ttk.Frame(row, style="Card.TFrame")
            cell.grid(row=0, column=col, sticky="w", padx=(0, 12))
            k = ttk.Label(cell, text="", style="SpecKey.TLabel")
            k.pack(anchor="w")
            v = tk.Entry(cell, bg=CARD, fg=TEXT, font=FONT_MID, relief="flat",
                         readonlybackground=CARD, highlightthickness=0,
                         state="readonly", width=34)
            v.pack(anchor="w")
            cells.append((k, v))
        spec_rows.append(cells)
    state["spec_cells"] = spec_rows
    tab_troph = ttk.Frame(nb)
    tab_images = ttk.Frame(nb)
    nb.add(tab_images, text="  Images  ")
    nb.add(tab_troph, text="  Trophies  ")
    state["troph_tab"] = tab_troph
    state["images_tab"] = tab_images
    # Images tab: big preview on top, one horizontal button row
    # pinned at the bottom (no side bar eating preview width)
    _imgbody = ttk.Frame(tab_images, style="Card.TFrame")
    _imgbody.pack(fill="both", expand=True)
    imgtablabel = tk.Label(_imgbody, bg=CARD, fg=MUTED, font=FONT_MID,
                           text="(no image)")
    imgtablabel.pack(fill="both", expand=True)
    state["imgtablabel"] = imgtablabel
    _imgbar = ttk.Frame(_imgbody, style="Card.TFrame")
    _imgbar.pack(fill="x", pady=(6, 0))
    mkbtn(_imgbar, text="< Prev", style="Ghost.TButton", bg=CARD,
          command=lambda: _step_image(-1)).pack(side="left")
    mkbtn(_imgbar, text="Next >", style="Ghost.TButton", bg=CARD,
          command=lambda: _step_image(1)).pack(side="left", padx=(6, 0))
    state["imgcombo"] = tk.StringVar(value="")
    imgcombo = ttk.Combobox(_imgbar, textvariable=state["imgcombo"],
                            state="readonly", width=16)
    imgcombo.pack(side="left", padx=(6, 0))
    imgcombo.bind("<<ComboboxSelected>>",
                  lambda _e: show_image(state["imgcombo"].get()))
    state["imgcombo_w"] = imgcombo
    mkbtn(_imgbar, text="Save", style="Ghost.TButton", bg=CARD,
          command=lambda: save_current_image()).pack(side="left", padx=(6, 0))
    mkbtn(_imgbar, text="Copy", style="Ghost.TButton", bg=CARD,
          command=lambda: copy_current_image()).pack(side="left", padx=(6, 0))
    state["imgtabcount"] = tk.StringVar(value="No images")
    tk.Label(_imgbar, textvariable=state["imgtabcount"], bg=CARD, fg=MUTED,
             font=FONT_SMALL).pack(side="right")
    def _sync_imgtab():
        # mirror the current cover into the Images tab preview
        try:
            lbl = state.get("imgtablabel")
            if lbl is None:
                return
            pil = state.get("pil")
            if pil is None:
                lbl.config(image="", text="(no image)")
                return
            try:
                from PIL import ImageTk as _ITk
            except Exception:
                lbl.config(image="", text="(no preview)")
                return
            im = pil.copy()
            try:
                _w0, _h0 = pil.size
            except Exception:
                _w0 = _h0 = 0
            # square covers (icon0 etc.) stretch to all the space the
            # tab offers; wide/tall banners keep their fixed boxes
            try:
                _ratio = (_w0 / _h0) if _h0 else 1.0
            except Exception:
                _ratio = 1.0
            if 0.9 <= _ratio <= 1.1:
                try:
                    lbl.update_idletasks()
                    _aw, _ah = lbl.winfo_width(), lbl.winfo_height()
                except Exception:
                    _aw = _ah = 0
                if _aw < 50 or _ah < 50:
                    _box = (300, 300)
                else:
                    _box = (max(_aw - 8, 200), max(_ah - 8, 200))
            elif _ratio > 1.1:
                _box = (480, 270)
            else:
                _box = (260, 340)
            im.thumbnail(_box)
            ph = _ITk.PhotoImage(im)
            state["imgtabphoto"] = ph
            lbl.config(image=ph, text="")
            lbl.image = ph
        except Exception:
            pass
    def _fill_imgtab(names):
        try:
            cb = state.get("imgcombo_w")
            if cb is None:
                return
            cb["values"] = list(names or [])
            if names:
                state["imgcombo"].set(names[0])
            else:
                state["imgcombo"].set("")
            state["imgtabcount"].set(
                f"{len(names)} images" if len(names) != 1 else "1 image")
        except Exception:
            pass
    trophsumvar = tk.StringVar(value="No trophies loaded")
    state["trophsumvar"] = trophsumvar
    _trophbar = ttk.Frame(tab_troph, style="Card.TFrame")
    _trophbar.pack(fill="x", pady=(0, 4))
    tk.Label(_trophbar, textvariable=trophsumvar, bg=CARD, fg=MUTED,
             font=FONT_SMALL, anchor="w", padx=10, pady=6).pack(side="left",
                                                                fill="x",
                                                                expand=True)
    mkbtn(_trophbar, text="Save icons...", style="Ghost.TButton", bg=CARD,
          command=lambda: save_trophy_icons()).pack(side="right",
                                                    padx=(0, 8))
    _tbody = ttk.Frame(tab_troph, style="Card.TFrame")
    _tbody.pack(fill="both", expand=True)
    trotv = ttk.Treeview(_tbody, columns=("id", "grade", "name"),
                         show="headings", height=14)
    trotv.heading("id", text="ID")
    trotv.heading("grade", text="Grade")
    trotv.heading("name", text="Name")
    trotv.column("id", width=40, anchor="center")
    trotv.column("grade", width=55, anchor="center")
    trotv.column("name", width=260)
    trotv.pack(side="left", fill="both", expand=True)
    _troprev = ttk.Frame(_tbody, style="Card.TFrame", width=175)
    _troprev.pack(side="right", fill="y", padx=(8, 0))
    _troprev.pack_propagate(False)
    # scrollable preview: banner + icon never get clipped on short windows
    _trocanvas = tk.Canvas(_troprev, bg=CARD, borderwidth=0,
                           highlightthickness=0, width=150)
    _troscroll = ttk.Scrollbar(_troprev, orient="vertical",
                               command=_trocanvas.yview)
    _trocanvas.configure(yscrollcommand=_troscroll.set)
    _troscroll.pack(side="right", fill="y")
    _trocanvas.pack(side="left", fill="both", expand=True)
    _troinner = tk.Frame(_trocanvas, bg=CARD)
    _trocanvas.create_window((0, 0), window=_troinner, anchor="nw")

    def _tro_scrollregion(_ev=None):
        try:
            _trocanvas.configure(scrollregion=_trocanvas.bbox("all"))
        except Exception:
            pass

    _troinner.bind("<Configure>", _tro_scrollregion)
    _trocanvas.bind("<MouseWheel>",
                    lambda _ev: _trocanvas.yview_scroll(
                        -1 * (_ev.delta // 120), "units"))
    trobanlbl = tk.Label(_troinner, bg=CARD, borderwidth=0,
                         highlightthickness=0)
    trobanlbl.pack(pady=(0, 4))
    # no fixed width/height: the label sizes to the image (no cropping)
    troimglbl = tk.Label(_troinner, bg=CARD, fg=MUTED, font=FONT_SMALL,
                         text="(no icon)")
    troimglbl.pack(pady=(0, 4))
    state["trotv"] = trotv
    state["troimglbl"] = troimglbl
    state["trobanlbl"] = trobanlbl
    trodetvar = tk.StringVar(value="Select a trophy for details")
    state["trodetvar"] = trodetvar
    tk.Label(tab_troph, textvariable=trodetvar, bg=CARD, fg=TEXT,
             font=FONT_SMALL, anchor="w", justify="left",
             wraplength=640, padx=10, pady=6).pack(fill="x", pady=(4, 0))
    state["trophy_path"] = None
    state["trophy_data"] = None

    tree = ttk.Treeview(tab_entries, columns=("id", "size", "codec"), show="tree headings")
    tree.heading("#0", text="name", anchor="w")
    tree.heading("id", text="id", anchor="w")
    tree.heading("size", text="size", anchor="e")
    tree.heading("codec", text="codec", anchor="w")
    tree.column("#0", width=300)
    tree.column("id", width=60)
    tree.column("size", width=110, anchor="e")
    tree.column("codec", width=80)
    sb = ttk.Scrollbar(tab_entries, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tree.pack(side="left", fill="both", expand=True)

    def extract_single():
        # Extract one Files-tab entry with rename (save-as dialog), streamed.
        import threading as _th
        from tkinter import filedialog as _fd
        r = state.get("result")
        if not r:
            statusvar.set("Open a file first")
            return
        sel = tree.selection()
        if not sel:
            statusvar.set("Select a file in the Files tab")
            return
        _iid = sel[0]
        # trophy-inner file: slice it out of the parent TRP entry
        if _iid in (state.get("trp_children") or {}):
            try:
                _pi, _in = state["trp_children"][_iid]
                _pe = r["entries"][_pi]
                _td = None
                if _pe.get("cached") is not None:
                    _td = bytes(_pe["cached"])
                elif isinstance(_pe.get("abs_off"), int) and _pe["abs_off"] >= 0:
                    _td = read_entry_bytes(r["path"], _pe["abs_off"],
                                           _pe["size"], limit=300_000_000)
                if not _td:
                    raise OSError("unreadable TRP")
                out = _fd.asksaveasfilename(title="Extract file as",
                                            initialfile=_in["name"],
                                            filetypes=[("All files", "*.*")])
                if not out:
                    return
                with open(out, "wb") as fw:
                    fw.write(_td[_in["off"]:_in["off"] + _in["size"]])
                statusvar.set(f"Extracted {_in['name']} "
                              f"({fmt_size(_in['size'])})")
            except Exception as ex:
                statusvar.set(f"Extract failed: {ex}")
            return
        try:
            e = r["entries"][int(_iid[1:])]
        except Exception:
            statusvar.set("Bad selection")
            return
        nm = (e.get("name") or "").strip() or f"entry_{e.get('id', 0)}"
        if e.get("size", 0) <= 0:
            statusvar.set("Empty entry — nothing to extract")
            return
        safe = nm.replace("/", "_").replace("\\", "_")
        out = _fd.asksaveasfilename(title="Extract file as",
                                    initialfile=safe,
                                    filetypes=[("All files", "*.*")])
        if not out:
            return

        def _work():
            try:
                total = e.get("size", 0)
                if e.get("local_path") and os.path.isfile(e["local_path"]):
                    with open(e["local_path"], "rb") as fh:
                        data = fh.read()
                    with open(out, "wb") as fw:
                        fw.write(data)
                    done = len(data)
                elif e.get("cached") is not None:
                    with open(out, "wb") as fw:
                        fw.write(e["cached"])
                    done = len(e["cached"])
                elif isinstance(e.get("abs_off"), int) and e["abs_off"] >= 0:
                    done = 0
                    with open(r["path"], "rb") as fh, open(out, "wb") as fw:
                        fh.seek(e["abs_off"])
                        left = total
                        while left > 0:
                            buf = fh.read(min(64 * 1024 * 1024, left))
                            if not buf:
                                break
                            fw.write(buf)
                            done += len(buf)
                            left -= len(buf)
                else:  # PS3-crypto / exfat chains: whole-read fallback
                    data = read_entry_bytes(r["path"], e["abs_off"], total,
                                            limit=2_000_000_000)
                    if not data:
                        raise OSError("unreadable entry")
                    with open(out, "wb") as fw:
                        fw.write(data)
                    done = len(data)
                root.after(0, statusvar.set,
                           f"Extracted {safe} ({fmt_size(done)})")
            except Exception as ex:
                root.after(0, statusvar.set, f"Extract failed: {ex}")

        statusvar.set(f"Extracting {safe}...")
        _th.Thread(target=_work, daemon=True).start()

    filectx = tk.Menu(root, tearoff=0, bg=CARD, fg=TEXT,
                      activebackground=ACCENT, activeforeground="#171717")
    filectx.add_command(label="Extract...",
                        command=lambda: extract_single())
    filectx.add_command(label="View trophies",
                        command=lambda: show_trophies())
    tree.bind("<Button-3>",
              lambda ev: (tree.selection_set(tree.identify_row(ev.y)),
                          filectx.tk_popup(ev.x_root, ev.y_root))
              if tree.identify_row(ev.y) else None)
    tree.bind("<Double-Button-1>", lambda ev: _tree_activate())

    def _tree_activate():
        # double-click a .trp pack -> trophy list; anything else -> extract
        try:
            sel = tree.selection()
            if sel:
                _iid = sel[0]
                if _iid.startswith("e") and "c" not in _iid:
                    _e = state.get("result", {}).get("entries", [])[int(_iid[1:])]
                    if (_e.get("name") or "").lower().endswith((".trp", ".ucp")):
                        show_trophies()
                        return
        except Exception:
            pass
        extract_single()

    def _trophy_reset(msg="No trophies loaded"):
        try:
            state["trotv"].delete(*state["trotv"].get_children())
        except Exception:
            pass
        for _k, _v in (("trophsumvar", msg),
                       ("trodetvar", "Select a trophy for details")):
            try:
                state[_k].set(_v)
            except Exception:
                pass
        try:
            state["troimglbl"].config(image="", text="(no icon)")
            state["trobanlbl"].config(image="")
        except Exception:
            pass
        state["trophy_data"] = None

    def _trophy_start(entry, result):
        # decrypt worker for one TRP/UCP entry; fills Trophies tab on done
        import threading as _th

        def _work():
            try:
                if entry.get("cached") is not None:
                    _td = bytes(entry["cached"])
                elif entry.get("local_path") and os.path.isfile(
                        entry["local_path"]):
                    with open(entry["local_path"], "rb") as _fh:
                        _td = _fh.read(300_000_000)
                else:
                    _td = read_entry_bytes(result["path"], entry["abs_off"],
                                           entry["size"], limit=300_000_000)
                if not _td:
                    raise OSError("unreadable trophy pack")
                if (entry.get("name") or "").lower().endswith(".ucp"):
                    _npid, _title, _trs, _icons = ucp_trophies(_td)
                    # online grades (background thread, never blocks UI);
                    # ring-color heuristic is the offline fallback.
                    # Guard: use online grades only if most UCP names match.
                    _grades = fetch_exophase_grades(_title)
                    if _grades:
                        try:
                            _hit = sum(1 for _t in _trs
                                       if _norm_name(_t.get("name", ""))
                                       in _grades)
                            if _hit * 2 < len(_trs):
                                _grades = {}
                        except Exception:
                            _grades = {}
                    root.after(0, lambda: _trophy_fill_ucp(
                        entry.get("name", ""), _npid, _trs, _icons, _grades))
                    return
                _inner = parse_trp(_td)
                _cands = [t for t in _inner
                          if t["name"].upper().startswith("TROP")
                          and t["name"].upper().endswith(".ESFM")
                          and t["size"] > 0]
                # language files (TROP_00.ESFM) carry names/details;
                # bare TROP.ESFM only has id/type/hidden skeleton
                def _tkey(t):
                    _un = t["name"].upper()
                    if _un == "TROP.ESFM":
                        return (1, _un)
                    if _un == "TROPCONF.ESFM":
                        return (2, _un)
                    return (0, _un)
                _cands.sort(key=_tkey)
                _npid, _xml, _fallback = None, None, None
                for _t in _cands:
                    _blob = _td[_t["off"]:_t["off"] + _t["size"]]
                    _n, _x = bruteforce_npid(_blob)
                    if _x and _fallback is None:
                        _fallback = (_n, _x)
                    if _x:
                        _ts = parse_trophy_xml(_x)
                        if any(_t2.get("name") for _t2 in _ts):
                            _npid, _xml = _n, _x
                            break
                if _xml is None and _fallback is not None:
                    _npid, _xml = _fallback
                _icons = carve_trp_icons(_td)
                root.after(0, lambda: _trophy_fill(
                    entry.get("name", ""), _npid, _xml, _icons, _td))
            except Exception as ex:
                root.after(0, statusvar.set, f"Trophy failed: {ex}")
                try:
                    root.after(0, state.update, {"trophy_loading": None})
                except Exception:
                    pass

        state["trophy_path"] = result["path"]
        _trophy_reset("Decrypting trophies (finding NP ID)...")
        state["trophy_loading"] = result["path"]
        statusvar.set("Decrypting trophies (finding NP ID)...")
        _th.Thread(target=_work, daemon=True).start()

    def _trophy_pick(entries):
        # prefer real trophy packs (trophy*.trp/ucp) over misc packs (uds*.ucp)
        cands = [x for x in (entries or [])
                 if (x.get("name") or "").lower().endswith((".trp", ".ucp"))
                 and x.get("size", 0) > 0]
        if not cands:
            return None
        cands.sort(key=lambda x: ("trophy" not in (x.get("name") or "").lower(),
                                  (x.get("name") or "")))
        return cands[0]

    def show_trophies():
        # jump to the Trophies tab (auto-filled on load); start the
        # worker here too if the tab isn't filled for this file yet.
        r = state.get("result")
        if not r:
            statusvar.set("Open a file first")
            return
        if state.get("trophy_loading") == r["path"]:
            try:
                nb.select(state["troph_tab"])
            except Exception:
                pass
            return
        sel = tree.selection()
        _e = None
        if sel:
            _iid = sel[0]
            if _iid.startswith("e") and "c" not in _iid:
                try:
                    _e = r["entries"][int(_iid[1:])]
                except Exception:
                    _e = None
        if _e is None or not (_e.get("name") or "").lower().endswith((".trp", ".ucp")):
            _e = _trophy_pick(r["entries"])
        try:
            nb.select(state["troph_tab"])
        except Exception:
            pass
        if _e is None:
            _trophy_reset("No trophy pack in this file")
            return
        if state.get("trophy_path") == r["path"] and state.get("trophy_data"):
            return
        _trophy_start(_e, r)

    def _sync_leftcover():
        # Images tab open -> left cover box shows image info text instead
        # of the same picture twice. Same box size: tabs never jump.
        try:
            if nb.select() == str(state.get("images_tab") or "") and \
                    state.get("pil") is not None:
                _nm = str(state.get("img_name") or "")
                try:
                    _w, _h = state["pil"].size
                except Exception:
                    _w = _h = 0
                _pos = ""
                try:
                    _vals = state.get("imgnames") or []
                    _pos = f"{_vals.index(state.get('img_name')) + 1}" \
                        f"/{len(_vals)}"
                except Exception:
                    pass
                _txt = _nm + (f"\n{_w}x{_h}" if _w else "") + \
                    (f"\n{_pos}" if _pos else "")
                imglabel.config(image="", text=_txt or "(no image)")
                return
            _ph = state.get("photo")
            if _ph is not None:
                imglabel.config(image=_ph, text="")
        except Exception:
            pass

    def _on_troph_tab(_ev=None):
        # lazy load: worker starts only when the Trophies tab is opened.
        try:
            _sel = nb.select()
        except Exception:
            return
        try:
            _sync_leftcover()
        except Exception:
            pass
        try:
            # Images tab just opened (or window resized): refit the
            # square preview to the space available
            if _sel == str(state.get("images_tab") or "") and \
                    state.get("pil") is not None:
                _sync_imgtab()
        except Exception:
            pass
        try:
            if _sel != str(state["troph_tab"]):
                return
        except Exception:
            return
        r = state.get("result")
        if not r or state.get("trophy_data"):
            return
        if state.get("trophy_loading") == r["path"]:
            return
        _e = _trophy_pick(r["entries"])
        if _e is None:
            _trophy_reset("No trophy pack in this file")
            return
        _trophy_start(_e, r)

    try:
        nb.bind("<<NotebookTabChanged>>", _on_troph_tab)
    except Exception:
        pass

    def save_trophy_icons():
        # Export every trophy icon (raw PNG bytes from the TRP) to a folder.
        # Files are named "000_Platinum_Trophy.png" etc.
        import threading as _th
        from tkinter import filedialog as _fd
        _dd = state.get("trophy_data") or {}
        _trs, _sq, _td = _dd.get("trs", []), _dd.get("sq", []), _dd.get("td")
        if not _trs or not _sq or _td is None:
            statusvar.set("No trophy icons loaded")
            return
        dest = _fd.askdirectory(title="Save trophy icons to folder")
        if not dest:
            return

        def _work():
            try:
                ok, skip = 0, 0
                for _idx, _t in enumerate(_trs):
                    if _idx >= len(_sq) or not _sq[_idx]:
                        skip += 1
                        continue
                    _ic = _sq[_idx]
                    _blob = _td[_ic["off"]:_ic["off"] + _ic["size"]]
                    if _blob[:8] != b"\x89PNG\r\n\x1a\n":
                        skip += 1
                        continue
                    _nm = sanitize_filename_part(
                        f"{_t['id']}_{_t['name'] or 'trophy'}") or f"trophy_{_idx}"
                    with open(os.path.join(dest, _nm + ".png"), "wb") as _fw:
                        _fw.write(_blob)
                    ok += 1
                root.after(0, statusvar.set,
                           f"Saved {ok} trophy icons to {dest}" +
                           (f" ({skip} skipped)" if skip else ""))
            except Exception as ex:
                root.after(0, statusvar.set, f"Save icons failed: {ex}")

        statusvar.set("Saving trophy icons...")
        _th.Thread(target=_work, daemon=True).start()

    def _trophy_fill_ucp(ucp_name, npid, trs, icons, grades=None):
        # fill the Trophies tab from a PS5 .ucp pack (no grades in UCP json).
        # Grade: online lookup first, ring-color heuristic as offline fallback.
        # Packs icon bytes into one blob so the shared preview/export code
        # (td + sq offsets) works unchanged.
        state["trophy_loading"] = None
        if not trs:
            _trophy_reset("No trophies parsed (UCP)")
            return
        _blob = bytearray()
        _sq = []
        for _t in trs:
            # UCP convention (verified vs official PSN art): trop0000 is the
            # trophy SET (title) art; trophy id N -> trop(N+1).png
            # 1:1 with trs (None = no icon) so names never shift out of sync
            _png = None
            try:
                _png = (icons or {}).get(f"trop{int(_t['id']) + 1:04d}.png")
            except Exception:
                _png = (icons or {}).get(f"trop{_t['id']}.png")
            _ok = False
            if _png is not None:
                try:
                    import struct as _st
                    _w, _h = _st.unpack_from(">2I", _png, 16)
                    _sq.append({"off": len(_blob), "size": len(_png),
                                "w": _w, "h": _h})
                    _blob += _png
                    _ok = True
                except Exception:
                    pass
            if not _ok:
                _sq.append(None)
        _td = bytes(_blob)
        _ban = [ic for ic in _sq if ic and ic["w"] != ic["h"]]
        # trop0000 (set/title art) as the preview banner when present
        _setart = (icons or {}).get("trop0000.png")
        if _setart and _setart[:4] == b"\x89PNG":
            try:
                import struct as _st
                _sw, _sh = _st.unpack_from(">2I", _setart, 16)
                _ban = ([{"off": len(_td), "size": len(_setart),
                          "w": _sw, "h": _sh}] + _ban)
                _td = _td + _setart
            except Exception:
                pass
        for _i, _t in enumerate(trs):
            _t["hidden"] = False
            _png = None
            try:
                _png = (icons or {}).get(f"trop{int(_t['id']) + 1:04d}.png")
            except Exception:
                pass
            # online grade first; else ring color with per-pack majority
            # calibration (bronze is always the biggest group)
            _g = (grades or {}).get(_norm_name(_t.get("name", ""))) or ""
            if _g not in ("P", "G", "S", "B"):
                _g = "RING:" + (_ucp_ring(_png) if _png else "")
            _t["type"] = _g
        try:
            from collections import Counter as _Counter
            _votes = _Counter(_t["type"] for _t in trs
                              if str(_t["type"]).startswith("RING:")
                              and _t["type"] != "RING:")
            _big = _votes.most_common(1)
            _big = _big[0][0] if _big else ""
            _rmap = {"RING:gold": "G", "RING:": ""}
            for _rc, _gg in (("RING:gray", "S"), ("RING:copper", "B")):
                if _big and _rc != _big:
                    _rmap[_rc] = _gg
            if _big in ("RING:gray", "RING:copper"):
                _rmap[_big] = "B"
            for _t in trs:
                if str(_t["type"]).startswith("RING:"):
                    _t["type"] = _rmap.get(_t["type"], "")
        except Exception:
            for _t in trs:
                if str(_t["type"]).startswith("RING:"):
                    _t["type"] = ""
        for _t in trs:
            if str(_t["id"]).strip() in ("0000", "0"):
                _t["type"] = "P"
        _have = sum(1 for ic in _sq if ic)
        _imap_note = ""
        if _have != len(trs):
            _imap_note = f" — icons {_have}/{len(trs)}"
        _trophy_reset(f"{len(trs)} trophies (UCP) — {npid or '?'}"
                      f"{_imap_note}")
        # NOTE: set AFTER _trophy_reset (it clears trophy_data)
        state["trophy_data"] = {"trs": trs, "sq": _sq, "td": _td,
                                "npid": npid, "thumbs": []}
        _tv = state["trotv"]
        try:
            _tv.bind("<<TreeviewSelect>>", _tro_on_sel)
        except Exception:
            pass
        try:
            import io as _io
            from PIL import Image as _Img, ImageTk as _ImgTk
            _has_pil = True
        except Exception:
            _has_pil = False
        for _idx, _t in enumerate(trs):
            _gtext = {"P": "Platinum", "G": "Gold",
                      "S": "Silver", "B": "Bronze"}.get(
                          _t["type"], _t["type"]) or "—"
            _kw = {"values": (_t["id"], _gtext, _t["name"])}
            if _has_pil and _idx < len(_sq) and _sq[_idx]:
                try:
                    _ic = _sq[_idx]
                    _tim = _Img.open(_io.BytesIO(
                        _td[_ic["off"]:_ic["off"] + _ic["size"]])).convert(
                        "RGBA")
                    _tim.thumbnail((28, 28))
                    _tph = _ImgTk.PhotoImage(_tim)
                    state["trophy_data"]["thumbs"].append(_tph)
                    _kw["image"] = _tph
                except Exception:
                    pass
            _tv.insert("", "end", **_kw)
        if _ban and _td:
            try:
                import io as _io
                from PIL import Image as _Img, ImageTk as _ImgTk
                _b = _ban[0]
                _bim = _Img.open(_io.BytesIO(
                    _td[_b["off"]:_b["off"] + _b["size"]])).convert("RGB")
                _bim.thumbnail((150, 84))
                _bph = _ImgTk.PhotoImage(_bim)
                state["trobanlbl"].config(image=_bph)
                state["trobanlbl"].image = _bph
            except Exception:
                pass
        try:
            _first = _tv.get_children()[0]
            _tv.selection_set(_first)
            _tro_on_sel()
        except Exception:
            pass

    def _trophy_fill(trp_name, npid, xml, icons=None, td=None):
        # fill the Trophies tab (main thread). Icon label has no fixed
        # size: it wraps the image instead of cropping it.
        state["trophy_loading"] = None
        if not xml:
            try:
                import cryptography  # noqa
                _trophy_reset("NP ID not found (tried NPWR00000-99999_00)")
                statusvar.set("NP ID not found (tried NPWR00000-99999_00)")
            except Exception:
                _trophy_reset("cryptography lib missing — can't decrypt")
                statusvar.set("cryptography lib missing — can't decrypt")
            return
        _trs = parse_trophy_xml(xml)
        if not _trs:
            _trophy_reset("No trophies parsed")
            return
        _grades = {}
        for _t in _trs:
            _grades[_t["type"]] = _grades.get(_t["type"], 0) + 1
        _hid = sum(1 for _t in _trs if _t["hidden"])
        _gtext = " ".join(f"{_grades.get(g, 0)}{g}"
                          for g in ("P", "G", "S", "B") if _grades.get(g))
        # square icons map to trophies in order; wide ones are title banners
        _sq = [ic for ic in (icons or []) if ic["w"] == ic["h"]]
        _ban = [ic for ic in (icons or []) if ic["w"] != ic["h"]]
        _imap_note = ""
        if _sq and len(_sq) != len(_trs):
            _imap_note = f" — icons {len(_sq)}/{len(_trs)} (order-mapped)"
        state["trophy_data"] = {"trs": _trs, "sq": _sq, "td": td,
                                "npid": npid}
        _trophy_reset(f"{len(_trs)} trophies ({_gtext}) — "
                      f"{_hid} hidden — {npid or '?'}"
                      f"{_imap_note}")
        state["trophy_data"] = {"trs": _trs, "sq": _sq, "td": td,
                                "npid": npid}
        _tv = state["trotv"]
        try:
            _tv.bind("<<TreeviewSelect>>", _tro_on_sel)
        except Exception:
            pass
        _GRADE = {"P": "Platinum", "G": "Gold",
                  "S": "Silver", "B": "Bronze"}
        for _t in _trs:
            _nm = _t["name"] + (" (hidden)" if _t["hidden"] else "")
            _tv.insert("", "end",
                       values=(_t["id"],
                               _GRADE.get(_t["type"], _t["type"]), _nm))
        # title banner on top of the preview pane, if the TRP has one
        if _ban and td:
            try:
                import io as _io
                from PIL import Image as _Img, ImageTk as _ImgTk
                _b = _ban[0]
                _bim = _Img.open(_io.BytesIO(
                    td[_b["off"]:_b["off"] + _b["size"]])).convert("RGB")
                _bim.thumbnail((150, 84))
                _bph = _ImgTk.PhotoImage(_bim)
                state["trobanlbl"].config(image=_bph)
                state["trobanlbl"].image = _bph
            except Exception:
                pass
        try:
            _first = _tv.get_children()[0]
            _tv.selection_set(_first)
            _tro_on_sel()
        except Exception:
            pass

    def _tro_on_sel(_ev=None):
        try:
            _tv = state["trotv"]
            _s = _tv.selection()
            if not _s:
                return
            _dd = state.get("trophy_data") or {}
            _trs = _dd.get("trs", [])
            _idx = _tv.index(_s[0])
            _t = _trs[_idx]
            state["trodetvar"].set(
                f"[{_t['id']}] {_t['name']}: {_t['detail'] or '—'}")
            _imglbl = state["troimglbl"]
            _sq = _dd.get("sq", [])
            _td = _dd.get("td")
            if not _sq or _td is None or _idx >= len(_sq) or not _sq[_idx]:
                _imglbl.config(image="", text="(no icon)")
                return
            import io as _io
            from PIL import Image as _Img, ImageTk as _ImgTk
            _ic = _sq[_idx]
            _im = _Img.open(_io.BytesIO(
                _td[_ic["off"]:_ic["off"] + _ic["size"]])).convert("RGBA")
            _im.thumbnail((150, 150))
            _ph = _ImgTk.PhotoImage(_im)
            _imglbl.config(image=_ph, text="")
            _imglbl.image = _ph
        except Exception:
            pass

    # badge strip inside the Specs tab, under the grid (moved out of
    # Details so everything spec-like lives in one place)
    detbadgerow = ttk.Frame(tab_specs, style="Card.TFrame")
    detbadgerow.pack(fill="x", pady=(0, 8))
    _blabs = []
    for _bv in state["badges"]:
        _lb = mkpill(detbadgerow, textvariable=_bv, parent_bg=CARD,
                     font=(FONT[0], 10, "bold"), padx=12, pady=5)
        # start hidden (empty): load() packs only the non-empty ones
        _lb.pack_forget()
        _blabs.append(_lb)
    state["badge_labels"] = _blabs
    metabar = ttk.Frame(tab_meta, style="Card.TFrame")
    metabar.pack(fill="x", pady=(0, 4))
    detailvar = tk.StringVar(value="Show all")
    mkbtn(metabar, text="Extract all", style="Ghost.TButton", bg=CARD,
          command=lambda: extract_all()).pack(side="left")
    mkbtn(metabar, text="Copy info", style="Ghost.TButton", bg=CARD,
          command=lambda: copy_all_info()).pack(side="left", padx=(8, 0))
    detailbtn = ttk.Button(metabar, textvariable=detailvar, style="Accent.TButton",
                           command=lambda: toggle_details())
    detailbtn.pack(side="right")
    metatext = tk.Text(tab_meta, bg=CARD, fg=TEXT, font=("Consolas", 9),
                       wrap="none", borderwidth=0, highlightthickness=0, padx=10, pady=10,
                        height=12, selectbackground=ACCENT,
                        selectforeground="#171717", insertbackground=TEXT)
    metatext.pack(fill="both", expand=True)
    metatext.tag_config("updates", foreground="#f0b429")
    root.bind_all("<KeyPress>", lambda e: _global_ctrl_keys(e, root, statusvar))
    ctxmenu = tk.Menu(root, tearoff=0, bg=CARD, fg=TEXT,
                      activebackground=ACCENT, activeforeground="#171717")
    ctxmenu.add_command(label="Copy",
                        command=lambda: copy_text_selection(metatext))
    ctxmenu.add_command(label="Select all",
                        command=lambda: select_all_text(metatext))
    metatext.bind("<Button-3>", lambda e: ctxmenu.tk_popup(e.x_root, e.y_root))

    # (bottombar created up top, before body, so it stays pinned)
    def _set_status(base=None):
        # persistent base (e.g. file entries) + update note, shown together
        try:
            if base is not None:
                state["status_base"] = base
            _b = state.get("status_base", "")
            _n = state.get("update_note", "")
            if _b and _n:
                statusvar.set(_b + "  •  " + _n)
            else:
                statusvar.set(_b or _n or "Ready")
        except Exception:
            pass

    def show_about():
        import webbrowser as _wb
        _ab = tk.Toplevel(root)
        _ab.title("About PKG Viewer")
        _ab.configure(bg=CARD)
        _ab.transient(root)
        _ab.grab_set()
        _ab.resizable(False, False)
        _logo = None
        try:
            from PIL import Image as _Img, ImageTk as _ImgTk
            import os as _os
            _base = getattr(sys, "_MEIPASS", _os.path.dirname(
                _os.path.abspath(__file__)))
            _p = _os.path.join(_base, "assets_about.png")
            if _os.path.exists(_p):
                _im = _Img.open(_p).convert("L")
                # crop to the dark mark, drop the white page background
                _bbox = _im.point(lambda v: 255 if v < 128 else 0).getbbox()
                if _bbox:
                    _im = _im.crop(_bbox)
                # dark mark -> near-white, background -> transparent (dark dialog)
                _a = _im.point(lambda v: 255 - v)
                _im = _Img.merge("RGBA", (_Img.new("L", _im.size, 0xf1),
                                          _Img.new("L", _im.size, 0xf3),
                                          _Img.new("L", _im.size, 0xf8), _a))
                _w = 190
                _h = max(1, round(_im.size[1] * _w / _im.size[0]))
                _logo = _ImgTk.PhotoImage(_im.resize((_w, _h), _Img.LANCZOS))
        except Exception:
            _logo = None
        if _logo is not None:
            tk.Label(_ab, image=_logo, bg=CARD).pack(padx=36, pady=(20, 0))
            _ab._logo_ref = _logo
        tk.Label(_ab, text="PKG Viewer %s" % APP_VERSION,
                 bg=CARD, fg=TEXT, font=FONT).pack(padx=36, pady=(12, 0))
        tk.Label(_ab, text="by Loopayeh",
                 bg=CARD, fg=MUTED, font=FONT_SMALL).pack(pady=(2, 0))
        tk.Label(_ab, text="View PS3 / PS4 / PS5 package info and cover art.",
                 bg=CARD, fg=TEXT, font=FONT_SMALL).pack(padx=36,
                                                         pady=(12, 0))
        tk.Label(_ab, text="If you enjoy what I build and want to support my work,\n"
                              "you can donate",
                 bg=CARD, fg=TEXT, font=FONT_SMALL, justify="center").pack(padx=36,
                                                                          pady=(12, 0))
        tk.Label(_ab, text="Every bit of support means a lot.\U0001F499",
                 bg=CARD, fg=TEXT, font=FONT_SMALL).pack(pady=(2, 0))
        tk.Label(_ab, text="USDT (BEP-20) — click address to copy:",
                 bg=CARD, fg=MUTED, font=FONT_SMALL).pack(pady=(8, 0))
        _addr = tk.Label(_ab, text=SUPPORT_ADDR,
                         bg=CARD, fg=TEXT, font=FONT_SMALL, cursor="hand2")
        _addr.pack(pady=(2, 0))

        def _copy_addr(_e=None):
            try:
                _ab.clipboard_clear()
                _ab.clipboard_append(SUPPORT_ADDR)
                _addr.config(text="copied ✓")
                _ab.after(1200, lambda: _addr.config(text=SUPPORT_ADDR))
            except Exception:
                pass
        _addr.bind("<Button-1>", _copy_addr)
        _links = ttk.Frame(_ab, style="Card.TFrame")
        _links.pack(pady=(14, 0))
        mkbtn(_links, text="Links  ↗", style="Ghost.TButton", bg=CARD,
               command=lambda: _wb.open(
                   "https://loopayeh.github.io/")).pack(side="left", ipadx=10, ipady=4)
        mkbtn(_links, text="Support  ↗", style="Ghost.TButton", bg=CARD,
               command=lambda: _wb.open(SUPPORT_URL)).pack(side="left", ipadx=10, ipady=4)
        mkbtn(_ab, text="Close", style="Accent.TButton", bg=CARD,
               command=_ab.destroy).pack(pady=(16, 20))
        # center over main window instead of top-left corner
        try:
            _ab.update_idletasks()
            _rx, _ry = root.winfo_x(), root.winfo_y()
            _rw, _rh = root.winfo_width(), root.winfo_height()
            _aw, _ah = _ab.winfo_width(), _ab.winfo_height()
            _ab.geometry("+%d+%d" % (_rx + (_rw - _aw) // 2,
                                     _ry + (_rh - _ah) // 2))
        except Exception:
            pass

    def check_updates(manual=False):
        """Check GitHub releases for a newer build (stdlib only)."""
        try:
            import updater as _up
        except Exception as e:
            if manual:
                statusvar.set("Update check failed: %s" % e)
            return
        if manual:
            statusvar.set("Checking for updates...")

        def _done(info):
            def _ui():
                if not info:
                    if manual:
                        statusvar.set("No releases found (or offline)")
                    return
                try:
                    newer = _up.is_newer(info.get("tag", ""), APP_VERSION)
                except Exception:
                    newer = False
                if newer:
                    try:
                        updatebtn.config(text="⬆ Update available",
                                         style="Accent.TButton")
                    except Exception:
                        pass
                    state["update_note"] = "Update available: %s" % info.get("tag", "")
                    _set_status()
                    if manual:
                        _show_update_dialog(info)
                elif manual:
                    state["update_note"] = "Up to date (%s)" % APP_VERSION
                    _set_status()
                    try:
                        messagebox.showinfo(
                            "No updates",
                            "You're up to date (%s)." % APP_VERSION,
                            parent=root)
                    except Exception:
                        pass
            try:
                root.after(0, _ui)
            except Exception:
                pass
        _up.check_in_background(UPDATE_REPO, _done)

    def _show_update_dialog(info):
        try:
            import updater as _up
        except Exception:
            return
        tag = info.get("tag", "")
        dlg = tk.Toplevel(root)
        dlg.title("Update available")
        dlg.configure(bg=BG)
        try:
            dlg.transient(root)
            dlg.grab_set()
        except Exception:
            pass
        tk.Label(dlg, text="A new version is available:", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(dlg, text="%s  (you have %s)" % (info.get("name", tag),
                                                  APP_VERSION),
                 bg=BG, fg=TEXT, font=FONT).pack(anchor="w", padx=16)
        _body = (info.get("body", "") or "").strip().split("\n")
        _notes = "\n".join(_body[:12])
        if _notes:
            _tx = tk.Text(dlg, bg=CARD, fg=TEXT, font=FONT_SMALL,
                          wrap="word", borderwidth=0, highlightthickness=0,
                          padx=10, pady=10,
                          height=8, width=60)
            _tx.pack(fill="both", expand=True, padx=16, pady=(10, 0))
            _tx.insert("end", _notes)
            _tx.config(state="disabled")
        _prog = tk.StringVar(value="")
        tk.Label(dlg, textvariable=_prog, bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(6, 0))
        _btns = tk.Frame(dlg, bg=BG)
        _btns.pack(fill="x", padx=16, pady=14)

        def _reenable():
            for _b in _btns.winfo_children():
                try:
                    _b.config(state="normal")
                except Exception:
                    pass

        def _dl_linux():
            try:
                _asset = _up.pick_deb_asset(info)
            except Exception:
                _asset = None
            if not _asset:
                _prog.set("No .deb found in this release")
                return
            _prog.set("Downloading %s..." % _asset["name"])
            for _b in _btns.winfo_children():
                try:
                    _b.config(state="disabled")
                except Exception:
                    pass

            def _work():
                try:
                    import tempfile as _tf
                    _tmp = _tf.mkdtemp(prefix="update_")
                    _dest = os.path.join(_tmp, _asset["name"])

                    def _pg(got, total):
                        if total:
                            root.after(0, _prog.set,
                                       "Downloading... %d%%"
                                       % (got * 100 // total))
                    _up.download(_asset["url"], _dest, progress=_pg)
                except Exception as e:
                    root.after(0, _prog.set, "Download failed: %s" % e)
                    root.after(0, _reenable)
                    return
                root.after(0, _prog.set,
                           "Installing update — confirm the password prompt...")
                try:
                    ok, msg = _up.install_deb(_dest)
                except Exception as e:
                    ok, msg = False, str(e)
                if ok:
                    def _rst():
                        _prog.set("Installed — restarting...")
                        try:
                            _up.relaunch_linux_app()
                        except Exception:
                            pass
                        try:
                            dlg.destroy()
                        except Exception:
                            pass
                        root.after(300, root.destroy)
                    root.after(0, _rst)
                else:
                    root.after(0, _prog.set,
                               "Install failed: %s (%s)" % (msg, _dest))
                    root.after(0, _reenable)
            import threading as _th
            _th.Thread(target=_work, daemon=True).start()

        def _dl():
            # installed builds only: Windows needs the Setup installer,
            # Linux installs the .deb (handled in _dl_linux).
            if sys.platform.startswith("linux"):
                _dl_linux()
                return
            try:
                _asset = _up.pick_setup_asset(info)
            except Exception:
                _asset = None
            if _asset is None:
                _prog.set("No installer found in this release")
                return
            _prog.set("Downloading %s..." % _asset["name"])
            for _b in _btns.winfo_children():
                try:
                    _b.config(state="disabled")
                except Exception:
                    pass

            def _work():
                try:
                    import tempfile as _tf
                    _tmp = _tf.mkdtemp(prefix="update_")
                    _dest = os.path.join(_tmp, _asset["name"])

                    def _pg(got, total):
                        if total:
                            root.after(0, _prog.set,
                                       "Downloading... %d%%"
                                       % (got * 100 // total))
                    _up.download(_asset["url"], _dest, progress=_pg)
                except Exception as e:
                    root.after(0, _prog.set, "Download failed: %s" % e)
                    return

                def _fin():
                    try:
                        root.after(0, _prog.set,
                                   "Installing update, app will restart...")
                        if _up.run_setup_and_exit(_dest):
                            try:
                                dlg.destroy()
                            except Exception:
                                pass
                            root.after(300, root.destroy)
                        else:
                            _prog.set("Update failed: cannot launch installer")
                    except Exception as e:
                        _prog.set("Update failed: %s" % e)
                root.after(0, _fin)
            import threading as _th
            _th.Thread(target=_work, daemon=True).start()
        mkbtn(_btns, text="Download + Install",
                   style="Accent.TButton", command=_dl).pack(side="left")
        mkbtn(_btns, text="Later", style="Ghost.TButton",
              command=dlg.destroy).pack(side="left", padx=(8, 0))
        _center_on_root(dlg)

    def _set_rename_enabled(on):
        try:
            renamebtn.config(state="normal" if on else "disabled")
        except Exception:
            pass

    def _set_undo_enabled(on):
        try:
            undobtn.config(state="normal" if on else "disabled")
        except Exception:
            pass

    def _refresh_path_after_move(old, new):
        r = state.get("result")
        if r and os.path.normcase(r.get("path") or "") == os.path.normcase(old):
            r["path"] = new
            try:
                pathvar.set(os.path.basename(new))
            except Exception:
                pass

    def undo_last_rename():
        pair = state.get("last_rename")
        if not pair:
            statusvar.set("Nothing to undo")
            return
        old_path, new_path = pair
        if not os.path.exists(new_path):
            statusvar.set("Undo failed: renamed file not found")
            state["last_rename"] = None
            _set_undo_enabled(False)
            return
        if os.path.exists(old_path):
            statusvar.set("Undo failed: original name is taken")
            return
        try:
            os.rename(new_path, old_path)
        except Exception as ex:
            statusvar.set(f"Undo failed: {ex}")
            return
        _refresh_path_after_move(new_path, old_path)
        state["last_rename"] = None
        _set_undo_enabled(False)
        _set_status(f"Undone: back to {os.path.basename(old_path)}")

    def _center_on_root(dlg, w=None, h=None):
        """Center a dialog over the main window (else screen center)."""
        try:
            dlg.update_idletasks()
            try:
                root.update_idletasks()
                rx, ry = root.winfo_rootx(), root.winfo_rooty()
                rw, rh = root.winfo_width(), root.winfo_height()
            except Exception:
                rx, ry, rw, rh = 0, 0, 0, 0
            dw = w or dlg.winfo_reqwidth()
            dh = h or dlg.winfo_reqheight()
            if rw > 1 and rh > 1:
                x = rx + max(0, (rw - dw) // 2)
                y = ry + max(0, (rh - dh) // 2)
            else:
                x = max(0, (dlg.winfo_screenwidth() - dw) // 2)
                y = max(0, (dlg.winfo_screenheight() - dh) // 2)
            if w and h:
                dlg.geometry("%dx%d+%d+%d" % (w, h, x, y))
            else:
                dlg.geometry("+%d+%d" % (x, y))
        except Exception:
            pass

    def show_rename():
        r = state.get("result")
        if not r:
            statusvar.set("Open a file first")
            return
        old_path = r.get("path") or ""
        if not old_path or not os.path.exists(old_path):
            statusvar.set("Original file not found")
            return
        base = build_clean_name(r)
        if not base:
            statusvar.set("Not enough info to build a name")
            return
        is_dir = os.path.isdir(old_path)
        _root, ext = os.path.splitext(os.path.basename(old_path)) if not is_dir else ("", "")
        suggested = base + ext
        dlg = tk.Toplevel(root)
        dlg.title("Rename file")
        dlg.configure(bg=BG)
        dlg.transient(root)
        dlg.grab_set()
        dlg.resizable(False, False)
        tk.Label(dlg, text="Old name:", bg=BG, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(fill="x", padx=14, pady=(12, 0))
        tk.Label(dlg, text=os.path.basename(old_path), bg=BG, fg=TEXT,
                 font=FONT, anchor="w", wraplength=420,
                 justify="left").pack(fill="x", padx=14)
        tk.Label(dlg, text="New name:", bg=BG, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(fill="x", padx=14, pady=(10, 0))
        namevar = tk.StringVar(value=suggested)
        entry = tk.Entry(dlg, textvariable=namevar, bg=CARD2, fg=TEXT,
                         font=FONT_MID, width=52, insertbackground=TEXT)
        entry.pack(fill="x", padx=14, pady=(2, 4))
        # name-part ticks: pick which components build the name
        partframe = tk.Frame(dlg, bg=BG)
        partframe.pack(fill="x", padx=14, pady=(2, 0))
        tk.Label(partframe, text="Include:", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(side="left")
        _pvars = {}

        def _parts_now():
            return {k: _pvars[k].get() for k, _ in NAME_PARTS}

        def _refresh_name(*_a):
            _b = build_clean_name(r, parts=_parts_now())
            if _b:
                namevar.set(_b + ext)
            else:
                msgvar.set("Tick at least one part")
        for _k, _lbl in NAME_PARTS:
            _v = tk.BooleanVar(value=True)
            _pvars[_k] = _v
            tk.Checkbutton(partframe, text=_lbl, variable=_v, bg=BG,
                           fg=TEXT, selectcolor=CARD2, activebackground=BG,
                           activeforeground=TEXT, font=FONT_SMALL,
                           command=_refresh_name).pack(side="left",
                                                       padx=(8, 0))
        entry.focus_set()
        entry.select_range(0, "end")
        msgvar = tk.StringVar(value="")
        tk.Label(dlg, textvariable=msgvar, bg=BG, fg="#e17b7b",
                 font=FONT_SMALL, anchor="w").pack(fill="x", padx=14)

        def _do_copy():
            try:
                root.clipboard_clear()
                root.clipboard_append(namevar.get().strip())
                msgvar.set("Copied to clipboard")
            except Exception as ex:
                msgvar.set(f"Copy failed: {ex}")

        def _do_rename():
            new_name = sanitize_filename_part(namevar.get(), limit=200)
            if not new_name:
                msgvar.set("Name is empty")
                return
            if not is_dir and "." not in new_name and ext:
                new_name += ext
            new_path = os.path.join(os.path.dirname(old_path), new_name)
            if os.path.normcase(new_path) == os.path.normcase(old_path):
                msgvar.set("Name unchanged")
                return
            if os.path.exists(new_path):
                msgvar.set("A file with this name already exists")
                return
            try:
                os.rename(old_path, new_path)
            except Exception as ex:
                msgvar.set(f"Error: {ex}")
                return
            r["path"] = new_path
            pathvar.set(os.path.basename(new_path))
            state["last_rename"] = (old_path, new_path)
            _set_undo_enabled(True)
            _set_status(f"Renamed to {os.path.basename(new_path)}")
            dlg.destroy()

        btns = tk.Frame(dlg, bg=BG)
        btns.pack(fill="x", padx=14, pady=(6, 14))
        mkbtn(btns, text="Rename", style="Accent.TButton",
              command=_do_rename).pack(side="left")
        mkbtn(btns, text="Copy", style="Ghost.TButton",
              command=_do_copy).pack(side="left", padx=(8, 0))
        mkbtn(btns, text="Cancel", style="Ghost.TButton",
              command=dlg.destroy).pack(side="right")
        _center_on_root(dlg)
        dlg.bind("<Return>", lambda _e: _do_rename())
        dlg.bind("<Escape>", lambda _e: dlg.destroy())

    def show_batch(files):        # single app folder / non-package file keeps the old load behavior —
        # unless the folder actually holds game files (then batch-scan it)
        if len(files) == 1:
            _p = files[0]
            if os.path.isdir(_p):
                try:
                    _has = any(fn.lower().endswith(BATCH_EXTS)
                               for fn in os.listdir(_p))
                except Exception:
                    _has = False
                if not _has:
                    load(_p)
                    return
            else:
                # single dropped/picked file always opens directly —
                # split-set siblings (_0.._N) are a batch-rename concern,
                # not a reason to hijack a single-file drop into batch.
                load(_p)
                return
        files = collect_batch_files(files)
        if not files:
            statusvar.set("No game files dropped")
            return
        if len(files) == 1 and len(split_set_siblings(files[0])) == 1:
            load(files[0])
            return
        try:
            statusvar.set(f"Scanning {len(files)} files...")
            root.update_idletasks()
            plan = preview_batch(files)
        except Exception as ex:
            statusvar.set(f"Error: {ex}")
            return
        dlg = tk.Toplevel(root)
        dlg.title(f"Batch rename ({len(plan)} items)")
        dlg.configure(bg=BG)
        dlg.transient(root)
        dlg.grab_set()
        dlg.geometry("840x540")
        _center_on_root(dlg, 840, 540)
        dlg.minsize(680, 420)
        try:
            dlg.resizable(True, True)
        except Exception:
            pass
        # bottom bar packed first so buttons never get pushed out of view
        btns = tk.Frame(dlg, bg=BG)
        btns.pack(side="bottom", fill="x", padx=14, pady=(6, 14))
        msgvar = tk.StringVar(value="All ready rows are selected. "
                                    "Double-click a row to exclude it.")
        _msg = tk.Label(dlg, textvariable=msgvar, bg=BG, fg=MUTED,
                        font=FONT_SMALL, anchor="w")
        _msg.pack(side="bottom", fill="x", padx=14)
        # name-part ticks: rebuild the plan with picked components
        partframe = tk.Frame(dlg, bg=BG)
        partframe.pack(side="top", fill="x", padx=12, pady=(12, 0))
        tk.Label(partframe, text="Include:", bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(side="left")
        _pvars = {}
        for _k, _lbl in NAME_PARTS:
            _v = tk.BooleanVar(value=True)
            _pvars[_k] = _v
            tk.Checkbutton(partframe, text=_lbl, variable=_v, bg=BG,
                           fg=TEXT, selectcolor=CARD2, activebackground=BG,
                           activeforeground=TEXT, font=FONT_SMALL,
                           command=lambda: _on_parts()).pack(side="left",
                                                             padx=(8, 0))
        cols = ("use", "old", "new", "status")
        tv = ttk.Treeview(dlg, columns=cols, show="headings", height=14)
        tv.heading("use", text="✓")
        tv.heading("old", text="current name")
        tv.heading("new", text="new name")
        tv.heading("status", text="status")
        tv.column("use", width=36, anchor="center")
        tv.column("old", width=240)
        tv.column("new", width=240)
        tv.column("status", width=180)
        sb = ttk.Scrollbar(dlg, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        tv.pack(side="top", fill="both", expand=True, padx=12, pady=(12, 6))
        checked = set()
        rows = []  # (plan_idx, old, new_or_None)

        def _rebuild_rows():
            del rows[:]
            checked.clear()
            for idx, item in enumerate(plan):
                if item["new_files"]:
                    for old, new in zip(item["files"], item["new_files"]):
                        rows.append((idx, old, new))
                else:
                    rows.append((idx, item["files"][0], None))
                if item["status"] == "ok":
                    checked.add(idx)

        def _on_parts():
            _inc = {k: _pvars[k].get() for k, _ in NAME_PARTS}
            try:
                plan[:] = preview_batch(files, include=_inc)
            except Exception as ex:
                msgvar.set(f"Error: {ex}")
                return
            try:
                dlg.title(f"Batch rename ({len(plan)} items)")
            except Exception:
                pass
            _rebuild_rows()
            _fill_rows()

        _rebuild_rows()

        def _status_text(idx):
            item = plan[idx]
            if item["status"] == "ok":
                return "renamed" if idx not in checked and \
                    item.get("_done") else "ready"
            return item["reason"] or "skip"

        def _fill_rows():
            for _iid in list(tv.get_children()):
                tv.delete(_iid)
            for idx, old, new in rows:
                tv.insert("", "end", iid=f"{idx}.{len(tv.get_children())}",
                          values=("✓" if idx in checked else "",
                                  os.path.basename(old),
                                  os.path.basename(new) if new else "—",
                                  _status_text(idx)))

        _fill_rows()

        def _toggle(_e=None):
            sel = tv.selection()
            if not sel:
                return
            try:
                idx = int(str(sel[0]).split(".")[0])
            except Exception:
                return
            if plan[idx]["status"] != "ok":
                return
            if idx in checked:
                checked.discard(idx)
            else:
                checked.add(idx)
            _fill_rows()

        tv.bind("<Double-Button-1>", _toggle)

        def _select_all():
            for idx, item in enumerate(plan):
                if item["status"] == "ok":
                    checked.add(idx)
            _fill_rows()

        def _select_none():
            checked.clear()
            _fill_rows()

        def _do_copy():
            try:
                lines = []
                for idx, item in enumerate(plan):
                    if item["new_files"]:
                        for old, new in zip(item["files"], item["new_files"]):
                            lines.append(f"{os.path.basename(old)}  ->  "
                                         f"{os.path.basename(new)}")
                root.clipboard_clear()
                root.clipboard_append("\n".join(lines))
                msgvar.set("Copied to clipboard")
            except Exception as ex:
                msgvar.set(f"Copy failed: {ex}")

        def _do_rename():
            sel = [plan[i] for i in sorted(checked)
                   if plan[i]["status"] == "ok"]
            if not sel:
                msgvar.set("Nothing selected")
                return
            renamed, skipped, lp = apply_batch(sel, log_path=default_batch_log())
            if lp:
                state["last_batch_log"] = lp
            state["last_rename"] = None
            _set_undo_enabled(False)
            for old, new in renamed:
                r = state.get("result")
                if r and os.path.normcase(r.get("path") or "") == \
                        os.path.normcase(old):
                    r["path"] = new
                    pathvar.set(os.path.basename(new))
            try:
                _set_status(f"Batch: renamed {len(renamed)}, "
                            f"skipped {len(skipped)}"
                            + (f" — log: {os.path.basename(lp)}" if lp else ""))
            except Exception:
                pass
            msgvar.set(f"Renamed {len(renamed)}, skipped {len(skipped)}."
                       + (f" Log: {lp}" if lp else ""))
            for item in sel:
                item["_done"] = True
            checked.clear()
            _fill_rows()

        # btns frame was packed at the bottom up-front; just add buttons
        mkbtn(btns, text="Rename selected", style="Accent.TButton",
              command=_do_rename).pack(side="left")
        mkbtn(btns, text="All", style="Ghost.TButton",
              command=_select_all).pack(side="left", padx=(8, 0))
        mkbtn(btns, text="None", style="Ghost.TButton",
              command=_select_none).pack(side="left", padx=(8, 0))
        mkbtn(btns, text="Copy list", style="Ghost.TButton",
              command=_do_copy).pack(side="left", padx=(8, 0))
        mkbtn(btns, text="Revert...", style="Ghost.TButton",
              command=lambda: show_revert()).pack(side="left", padx=(8, 0))
        mkbtn(btns, text="Close", style="Ghost.TButton",
              command=dlg.destroy).pack(side="right")

    def show_revert(log_path=None):
        """Pick a batch_rename_*.log, preview it, revert selected rows."""
        if not log_path:
            _init = os.path.dirname(state.get("last_batch_log") or "") or "."
            log_path = filedialog.askopenfilename(
                title="Select revert log",
                initialdir=_init,
                filetypes=[("Revert log", "batch_rename_*.log"),
                           ("Log files", "*.log"),
                           ("All files", "*.*")])
            if not log_path:
                return
        pairs = parse_revert_log(log_path)
        if not pairs:
            statusvar.set(f"Revert: no valid entries in "
                          f"{os.path.basename(log_path)}")
            return
        try:
            from tkinter import messagebox as _mb
        except Exception:
            _mb = None
        rdlg = tk.Toplevel(root)
        rdlg.title(f"Revert ({len(pairs)} entries)")
        rdlg.configure(bg=BG)
        rdlg.transient(root)
        rdlg.grab_set()
        rdlg.geometry("840x480")
        _center_on_root(rdlg, 840, 480)
        rdlg.minsize(680, 380)
        try:
            rdlg.resizable(True, True)
        except Exception:
            pass
        rbtns = tk.Frame(rdlg, bg=BG)
        rbtns.pack(side="bottom", fill="x", padx=14, pady=(6, 14))
        rmsg = tk.StringVar(value=f"From: {os.path.basename(log_path)} — "
                                  "double-click a row to exclude it.")
        tk.Label(rdlg, textvariable=rmsg, bg=BG, fg=MUTED,
                 font=FONT_SMALL, anchor="w").pack(side="bottom", fill="x",
                                                   padx=14)
        rcols = ("use", "current", "restore", "status")
        rtv = ttk.Treeview(rdlg, columns=rcols, show="headings", height=14)
        rtv.heading("use", text="✓")
        rtv.heading("current", text="current name")
        rtv.heading("restore", text="restore to")
        rtv.heading("status", text="status")
        rtv.column("use", width=36, anchor="center")
        rtv.column("current", width=240)
        rtv.column("restore", width=240)
        rtv.column("status", width=180)
        rsb = ttk.Scrollbar(rdlg, orient="vertical", command=rtv.yview)
        rtv.configure(yscrollcommand=rsb.set)
        rsb.pack(side="right", fill="y")
        rtv.pack(side="top", fill="both", expand=True, padx=12, pady=(12, 6))
        rchecked = set(range(len(pairs)))

        def _rstatus(i):
            cur, rst = pairs[i]
            if not os.path.exists(cur):
                return "missing"
            if os.path.exists(rst):
                return "target exists"
            return "ready"

        def _rfill():
            for _iid in list(rtv.get_children()):
                rtv.delete(_iid)
            for i, (cur, rst) in enumerate(pairs):
                rtv.insert("", "end", iid=str(i),
                           values=("✓" if i in rchecked else "",
                                   os.path.basename(cur),
                                   os.path.basename(rst),
                                   _rstatus(i)))

        _rfill()

        def _rtoggle(_e=None):
            sel = rtv.selection()
            if not sel:
                return
            try:
                i = int(str(sel[0]))
            except Exception:
                return
            if i in rchecked:
                rchecked.discard(i)
            else:
                rchecked.add(i)
            _rfill()

        rtv.bind("<Double-Button-1>", _rtoggle)

        def _rall():
            rchecked.update(range(len(pairs)))
            _rfill()

        def _rnone():
            rchecked.clear()
            _rfill()

        def _rdo():
            sel = [(pairs[i][0], pairs[i][1]) for i in sorted(rchecked)
                   if _rstatus(i) == "ready"]
            if not sel:
                rmsg.set("Nothing ready selected")
                return
            if _mb is not None:
                try:
                    if not _mb.askyesno(
                            "Confirm revert",
                            f"Rename {len(sel)} file(s) back to their "
                            f"original names?"):
                        return
                except Exception:
                    pass
            rev, skip = apply_revert(sel)
            for cur, rst in rev:
                _refresh_path_after_move(cur, rst)
            try:
                _set_status(f"Revert: restored {len(rev)}, "
                            f"skipped {len(skip)}")
            except Exception:
                pass
            rmsg.set(f"Restored {len(rev)}, skipped {len(skip)}.")
            rdlg.destroy()

        mkbtn(rbtns, text="Revert selected", style="Accent.TButton",
              command=_rdo).pack(side="left")
        mkbtn(rbtns, text="All", style="Ghost.TButton",
              command=_rall).pack(side="left", padx=(8, 0))
        mkbtn(rbtns, text="None", style="Ghost.TButton",
              command=_rnone).pack(side="left", padx=(8, 0))
        mkbtn(rbtns, text="Close", style="Ghost.TButton",
              command=rdlg.destroy).pack(side="right")

    # logic
    def pick():
        p = filedialog.askopenfilename(title="Select PKG / image file",
                                       filetypes=[("Game files", "*.pkg *.exfat *.ffpfsc *.ffpkg"),
                                                  ("PKG", "*.pkg"),
                                                  ("exFAT image", "*.exfat"),
                                                  ("all", "*.*")])
        if p:
            load(p)
        else:
            d = filedialog.askdirectory(title="...or select an app folder")
            if d:
                load(d)

    def pick_many():
        ps = filedialog.askopenfilenames(title="Select files for batch rename",
                                         filetypes=[("Game files", "*.pkg *.exfat *.ffpfsc *.ffpkg"),
                                                    ("all", "*.*")])
        if ps:
            show_batch(list(ps))
        else:
            d = filedialog.askdirectory(title="...or select a folder to batch-scan")
            if d:
                show_batch([d])

    def show_tab(idx):
        # Extra > List Contents (Files) / Package Update note (Details).
        try:
            nbw = state.get("notebook")
            if nbw is not None:
                nbw.select(idx)
        except Exception:
            pass

    def check_integrity():
        # LMAN-style "Check Integrity": entry bounds vs real file size.
        import os as _os
        r = state.get("result")
        if not r:
            statusvar.set("Open a file first")
            return
        try:
            fsize = _os.path.getsize(r["path"]) if _os.path.isfile(r["path"]) else r.get("size", 0)
        except OSError:
            fsize = r.get("size", 0)
        bad = []
        for e in r.get("entries", []):
            off, sz = e.get("abs_off"), e.get("size", 0)
            if isinstance(off, int) and off >= 0 and sz > 0:
                if off < 0 or off + sz > fsize:
                    bad.append(e.get("name") or str(e.get("id")))
        if bad:
            statusvar.set(f"Integrity: {len(bad)} bad entries ({', '.join(bad[:3])})")
        else:
            n = len([e for e in r.get("entries", []) if e.get("name")])
            statusvar.set(f"Integrity OK - {n} entries within bounds")

    def show_properties():
        # LMAN-style "Properties" popup: full Param = Value table.
        r = state.get("result")
        if not r:
            statusvar.set("Open a file first")
            return
        win = tk.Toplevel(root)
        win.title("Properties - %s" % os.path.basename(r.get("path", "")))
        win.configure(bg=CARD)
        win.transient(root)
        rows = list(r.get("rows", []))
        txt = tk.Text(win, bg=CARD, fg=TEXT, font=("Consolas", 9),
                      borderwidth=0, highlightthickness=0, padx=12, pady=12,
                      height=min(max(len(rows) + 2, 10), 30), width=70)
        txt.pack(fill="both", expand=True)
        for k, v in rows:
            txt.insert("end", f"{k} = {v}\n")
        txt.config(state="disabled")
        mkbtn(win, text="Close", style="Accent.TButton", bg=CARD,
              command=win.destroy).pack(pady=(0, 12))

    def extract_all():
        # LMAN-style "Extract Package": dump every listed entry to a folder.
        from tkinter import filedialog as _fd
        r = state.get("result")
        if not r or not r.get("entries"):
            statusvar.set("Nothing to extract")
            return
        dest = _fd.askdirectory(title="Extract package to folder")
        if not dest:
            return
        ok, fail = 0, 0
        for e in r["entries"]:
            nm = (e.get("name") or "").strip()
            if not nm or e.get("size", 0) <= 0:
                continue
            safe = nm.replace("/", "_").replace("\\", "_")
            try:
                if e.get("local_path") and os.path.isfile(e["local_path"]):
                    with open(e["local_path"], "rb") as fh:
                        data = fh.read()
                elif e.get("cached") is not None:
                    data = e["cached"]
                else:
                    data = read_entry_bytes(r["path"], e["abs_off"], e["size"],
                                            limit=2_000_000_000)
                if not data:
                    fail += 1
                    continue
                with open(os.path.join(dest, safe), "wb") as out:
                    out.write(data)
                ok += 1
            except Exception:
                fail += 1
        statusvar.set(f"Extracted {ok} files" + (f" ({fail} skipped)" if fail else ""))

    def copy_update_link():
        # LMAN-style "CopyLinks": copy the patch-tracker page for this
        # title (direct Sony links are blocked; orbispatches needs a
        # browser session for its Download buttons, so deep-link it).
        r = state.get("result")
        tid = (r.get("patch_tid") or "").upper() if r else ""
        if not tid:
            statusvar.set("No title ID for update link")
            return
        host = _PATCH_HOST.get(tid[:4], "https://orbispatches.com")
        url = host.rstrip("/") + "/" + tid
        try:
            root.clipboard_clear()
            root.clipboard_append(url)
            statusvar.set(f"Update page copied: {url}")
        except Exception as ex:
            statusvar.set(f"Copy failed: {ex}")

    def copy_all_info():
        # Copy everything about the open file: header rows + Details text.
        r = state.get("result")
        if not r:
            statusvar.set("Open a file first")
            return
        try:
            parts = [f"File = {r.get('path', '')}", ""]
            for k, v in r.get("rows", []):
                parts.append(f"{k} = {v}")
            try:
                det = metatext.get("1.0", "end-1c").strip()
            except Exception:
                det = ""
            if det:
                parts += ["", "-- Details --", det]
            root.clipboard_clear()
            root.clipboard_append("\n".join(parts))
            statusvar.set("Info copied to clipboard")
        except Exception as ex:
            statusvar.set(f"Copy failed: {ex}")

    def load(p):
        statusvar.set("Reading...")
        root.update_idletasks()
        try:
            r = parse_pkg(p)
        except Exception as e:
            statusvar.set(f"Error: {e}")
            _set_rename_enabled(False)
            return
        if not r.get("ok"):
            statusvar.set("Error: " + r.get("error", "?"))
            _set_rename_enabled(False)
            return
        state["result"] = r
        state["show_all"] = False
        detailvar.set("Show all")
        pathvar.set(os.path.basename(p))
        titlevar.set(r["title"])
        try:
            _ext = os.path.splitext(p)[1].lower()
            _fmt = {".ffpkg": "ffpkg", ".ffpfsc": "ffpfsc",
                    ".exfat": "exfat", ".pkg": "pkg"}.get(_ext, "")
            _fl = state.get("fmtlabel")
            if _fl is not None:
                if _fmt and has_pil:
                    _fim = _format_icon_image(_fmt, (28, 28))
                    if _fim is not None:
                        _fph = ImageTk.PhotoImage(_fim)
                        state["fmt_photo"] = _fph
                        _fl.config(image=_fph, text="")
                    else:
                        state["fmt_photo"] = None
                        _fl.config(image="", text="")
                else:
                    state["fmt_photo"] = None
                    _fl.config(image="", text="")
        except Exception:
            pass
        plat = r["rows"][0][1] if r["rows"] else ""
        _rd = dict(r["rows"])
        badges = state.get("badges", [])
        _blabs = state.get("badge_labels", [])
        _type = _rd.get("Type", "")
        _has_lz4 = "LZ4" in _rd.get("Assets", "")
        _b0 = "LZ4" if _has_lz4 else plat
        _pkg = _rd.get("Package", "")
        _pl2 = _pkg.lower()
        if "fake" in _pl2 or "fpkg" in _pl2:
            _pkg_short, _pkg_col = "FPKG", "#e17b7b"
        elif "official" in _pl2 or _pl2.startswith("ofc"):
            _pkg_short, _pkg_col = "OFC", "#10b981"
        else:
            _pkg_short, _pkg_col = "", "#6b7280"
        _bvals = [_b0,
                  _rd.get("Region", ""),
                  f"{fmt_size(r['size'])}",
                  _type,
                  _pkg_short]
        _pl = plat.lower()
        if _has_lz4:
            _plat_col = "#6fd3c9"
        elif "ffpkg" in _pl:
            _plat_col = "#9b6ddb"
        elif "ffpfsc" in _pl:
            _plat_col = "#f2b84b"
        elif "exfat" in _pl:
            _plat_col = "#3dd6b0"
        elif "ps3" in _pl:
            _plat_col = "#e8a34c"
        elif "ps4" in _pl or _pl.startswith("cnt"):
            _plat_col = "#5fa8ff"
        elif "ps5" in _pl:
            _plat_col = "#f1f3f8"
        else:
            _plat_col = "#6b7280"
        _tl = _type.lower()
        _type_col = ("#5fa8ff" if "update" in _tl
                     else "#f59e5b" if ("dlc" in _tl or "patch" in _tl)
                     else "#10b981" if _type else "#6b7280")
        _bcolors = [_plat_col, "#e17b7b", "#6b7280", _type_col, _pkg_col]
        for i, (bv, val, lb, col) in enumerate(zip(badges, _bvals, _blabs, _bcolors)):
            bv.set(val or "")
            try:
                lb.config(bg=col, fg="#171717")
            except Exception:
                pass
            # dumps (e.g. PS5 folders) have no Package row: hide the
            # empty pill instead of leaving a blank badge
            try:
                if val:
                    lb.pack(side="left", padx=(0, 8), pady=2)
                else:
                    lb.pack_forget()
            except Exception:
                pass
        _flat = [(k, v) for (k, v) in r["rows"]
                 if k not in ("Platform", "Size", "Region")]
        _flat = _flat[:10]
        cells = [c for row in state.get("spec_cells", []) for c in row]
        for (k, v), (kl, vl) in zip(_flat, cells):
            kl.config(text=k.upper())
            vl.config(state="normal")
            vl.delete(0, "end")
            vl.insert(0, str(v)[:60])
            vl.config(state="readonly")
        for kl, vl in cells[len(_flat):]:
            kl.config(text="")
            vl.config(state="normal")
            vl.delete(0, "end")
            vl.config(state="readonly")
        tree.delete(*tree.get_children())
        state["trp_children"] = {}
        for idx, e in enumerate(r["entries"]):
            if not e["name"]:
                continue
            tree.insert("", "end", iid=f"e{idx}", text=e["name"],
                        values=(e["id"], fmt_size(e["size"]), e.get("codec", "")))
            # trophy pack: expand inner TRP/UCP files as tree children
            if e["name"].lower().endswith((".trp", ".ucp")) and 0 < e["size"] < 300_000_000:
                try:
                    _td = None
                    if e.get("cached") is not None:
                        _td = bytes(e["cached"])
                    elif e.get("local_path") and os.path.isfile(
                            e["local_path"]):
                        with open(e["local_path"], "rb") as _fh:
                            _td = _fh.read(300_000_000)
                    elif e.get("abs_off") is not None:
                        _td = read_entry_bytes(r["path"], e["abs_off"],
                                               e["size"], limit=300_000_000)
                    _is_ucp = e["name"].lower().endswith(".ucp")
                    _inner = ((parse_ucp(_td) if _is_ucp else parse_trp(_td))
                              if _td else [])
                except Exception:
                    _inner = []
                for j, _in in enumerate(_inner):
                    _iid = f"e{idx}c{j}"
                    state["trp_children"][_iid] = (idx, _in)
                    tree.insert(f"e{idx}", "end", iid=_iid,
                                text="↳ " + _in["name"],
                                values=("", fmt_size(_in["size"]), "trp"))
        # Trophies tab: lazy — loads only when the tab is opened
        # (no trophy work during file load)
        state["trophy_path"] = None
        state["trophy_loading"] = None
        _trophy_reset("Open the Trophies tab to load")
        metatext.delete("1.0", "end")
        refresh_details()
        # image choices: png entries
        pngs = [e["name"] for e in r["entries"]
                if e["name"].lower().endswith(".png") and e["size"] > 0]
        state["imgnames"] = pngs
        _fill_imgtab(pngs)
        if pngs:
            first = "icon0.png" if "icon0.png" in pngs else pngs[0]
            show_image(first)
        elif r.get("store_cid"):
            state["pil"] = None
            _sync_imgtab()
            _fill_imgtab([])
            imglabel.config(image="", text="Fetching cover...")
            fetch_store_async(r["store_cid"])
        else:
            state["pil"] = None
            _sync_imgtab()
            _fill_imgtab([])
            imglabel.config(image="", text="(no image)")
        if r.get("patch_tid"):
            fetch_patch_async(r["patch_tid"], r.get("own_ver", ""))
        _set_rename_enabled(True)
        _summ = lman_summary(r.get("kind"), dict(r["rows"]))
        _set_status((_summ + f"  •  {len(r['entries'])} entries") if _summ else
                    f"OK - {len(r['entries'])} entries")

    def refresh_details():
        r = state.get("result")
        metatext.delete("1.0", "end")
        if not r:
            return
        if state.get("show_all"):
            lines = full_meta_lines(r.get("meta"))
        else:
            lines = curated_meta_lines(r.get("kind"), r.get("meta"))
        if r.get("ampr_lines"):
            lines = list(lines) + ["", "-- AMPR containers --"] + list(r["ampr_lines"])
        if r.get("store_lines"):
            lines = list(lines) + ([""] if lines else []) + \
                ["-- PlayStation Store --"] + list(r["store_lines"])
        if r.get("patch_lines"):
            lines = list(lines) + ([""] if lines else []) + \
                ["-- Updates --"] + list(r["patch_lines"])
        metatext.insert("end", "\n".join(lines) + ("\n" if lines else ""))
        # highlight the "-- Updates --" (patch tracker) section in amber
        # + embed a Copy link button right on its header line.
        try:
            for i, ln in enumerate(lines, start=1):
                if ln.strip() == "-- Updates --":
                    metatext.tag_add("updates", f"{i}.0", "end-1c")
                    try:
                        _cb = tk.Button(metatext, text="Copy link",
                                        bg=CARD2, fg=TEXT, relief="flat",
                                        font=FONT_SMALL, cursor="hand2",
                                        padx=8, pady=0,
                                        activebackground=ACCENT,
                                        activeforeground="#171717",
                                        command=lambda: copy_update_link())
                        metatext.window_create(f"{i}.end", window=_cb)
                        state["copylink_embed"] = _cb  # keep a ref
                    except Exception:
                        pass
                    break
        except Exception:
            pass

    def toggle_details():
        state["show_all"] = not state.get("show_all")
        detailvar.set("Show less" if state["show_all"] else "Show all")
        refresh_details()

    def copy_text_selection(widget):
        try:
            sel = widget.get("sel.first", "sel.last")
        except Exception:
            sel = widget.get("1.0", "end-1c")
        root.clipboard_clear()
        root.clipboard_append(sel)
        statusvar.set("Text copied")
        return "break"

    def select_all_text(widget):
        widget.tag_add("sel", "1.0", "end-1c")
        return "break"

    def save_current_image():
        r = state.get("result")
        name = state.get("img_name")
        if not r or not name:
            statusvar.set("No image selected")
            return
        e = next((x for x in r["entries"] if x["name"] == name), None)
        data = state.get("store_bytes") if (not e and name == "cover.jpg") else None
        if data is None:
            if not e:
                return
            data = e.get("cached")
        if data is None:
            data = read_entry_bytes(r["path"], e["abs_off"], e["size"])
        if data[:8] != b"\x89PNG\r\n\x1a\n" and data[:2] != b"\xff\xd8":
            statusvar.set("Not an image")
            return
        dest = filedialog.asksaveasfilename(
            title="Save image", defaultextension=".png",
            initialfile=name.replace("/", "_"),
            filetypes=[("PNG", "*.png"), ("all", "*.*")])
        if not dest:
            return
        try:
            with open(dest, "wb") as out:
                out.write(data)
            statusvar.set(f"Saved {os.path.basename(dest)}")
        except Exception as ex:
            statusvar.set(f"Error: {ex}")

    def copy_current_image():
        pil = state.get("pil")
        if pil is None:
            statusvar.set("No image to copy")
            return
        err = copy_image_to_clipboard(pil)
        statusvar.set("Copied to clipboard" if err is None else f"Copy failed: {err}")

    def display_pil(im, label):
        """Render a PIL image on the fixed canvas. Returns None or error str."""
        try:
            state["pil"] = im.copy()
            state["img_name"] = label
            im.thumbnail((260, 260))
            canvas = Image.new("RGB", (280, 280), CARD)
            canvas.paste(im, ((280 - im.size[0]) // 2,
                              (280 - im.size[1]) // 2))
            ph = ImageTk.PhotoImage(canvas)
            state["photo"] = ph
            imglabel.config(image=ph, text="")
            imglabel.image = ph
            _sync_imgtab()
            _sync_leftcover()
            return None
        except Exception as ex:
            return str(ex)

    def fetch_store_async(cid):
        """Background: store cover + title → display via root.after."""
        def _work():
            try:
                name, url, rel, tag = fetch_store_cover(cid)
            except Exception:
                name, url, rel, tag = None, None, None, None
            data = b""
            if url:
                try:
                    data = download_url_bytes(url) or b""
                except Exception:
                    data = b""
            try:
                root.after(0, lambda: _store_done(name, data, rel, tag))
            except Exception:
                pass
        import threading as _th
        _th.Thread(target=_work, daemon=True).start()

    def _store_done(name, data, rel, tag):
        r = state.get("result")
        if not r or not r.get("store_cid"):
            return
        if name and name != r["title"]:
            titlevar.set(name)
            r["title"] = name
        lines = []
        if name:
            lines.append(f"Title = {name}")
        if rel:
            lines.append(f"Release = {rel}")
        if tag:
            lines.append(f"Tagline = {tag}")
        if lines:
            r["store_lines"] = lines
            refresh_details()
        state["store_bytes"] = data if data[:8] == b"\x89PNG\r\n\x1a\n" or \
            data[:2] == b"\xff\xd8" else b""
        if not state["store_bytes"]:
            imglabel.config(image="", text="(cover unavailable)")
            return
        if not has_pil:
            imglabel.config(text="(Pillow not installed)")
            return
        try:
            im = Image.open(io.BytesIO(state["store_bytes"]))
        except Exception:
            imglabel.config(image="", text="(bad image)")
            return
        err = display_pil(im, "cover.jpg")
        if err:
            imglabel.config(text="(bad image)")
            statusvar.set(f"Error: {err}")
        else:
            state["imgnames"] = ["cover.jpg"]
            _fill_imgtab(["cover.jpg"])
            statusvar.set("OK - store cover")

    def fetch_patch_async(tid, own_ver):
        """Background: latest patch version → Details via root.after."""
        def _work():
            try:
                latest, count, date = fetch_latest_patch(tid)
            except Exception:
                latest, count, date = None, 0, ""
            try:
                root.after(0, lambda: _patch_done(tid, own_ver, latest, count, date))
            except Exception:
                pass
        import threading as _th
        _th.Thread(target=_work, daemon=True).start()

    def _patch_done(tid, own_ver, latest, count, date):
        r = state.get("result")
        if not r or r.get("patch_tid") != tid:
            return
        if not latest:
            return
        ago = _ago(date)
        line1 = f"Latest patch = {latest} ({count} known)"
        if date:
            line1 += f" — {date[:10]}" + (f" ({ago})" if ago else "")
        lines = [line1]
        if own_ver:
            lines.append(f"PKG version = {own_ver} " +
                         ("(up to date)" if own_ver.strip() == latest.strip()
                          else "(behind latest)"))
        else:
            lines.append("PKG version unknown (encrypted)")
        r["patch_lines"] = lines
        refresh_details()

    def show_image(name):
        r = state.get("result")
        if not r:
            return
        e = next((x for x in r["entries"] if x["name"] == name), None)
        if not e:
            return
        statusvar.set(f"Extracting {name}...")
        root.update_idletasks()
        try:
            if e.get("local_path") and os.path.isfile(e["local_path"]):
                with open(e["local_path"], "rb") as fh:
                    data = fh.read()
            elif e.get("cached") is not None:
                data = e["cached"]
            else:
                data = read_entry_bytes(r["path"], e["abs_off"], e["size"])
        except Exception as ex:
            statusvar.set(f"Error: {ex}")
            return
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            imglabel.config(image="", text="(not a PNG)")
            statusvar.set("OK")
            return
        if not has_pil:
            imglabel.config(text=f"PNG {fmt_size(len(data))}\n(Pillow not installed)")
            statusvar.set("OK")
            return
        try:
            im = Image.open(io.BytesIO(data))
            state["pil"] = im.copy()
            state["img_name"] = name
            im.thumbnail((260, 260))
            # fixed-size canvas: pad with card bg so layout never shifts
            canvas = Image.new("RGB", (280, 280), CARD)
            canvas.paste(im, ((280 - im.size[0]) // 2,
                              (280 - im.size[1]) // 2))
            ph = ImageTk.PhotoImage(canvas)
            state["photo"] = ph
            imglabel.config(image=ph, text="")
            imglabel.image = ph
            _sync_imgtab()
            _sync_leftcover()
            statusvar.set(f"OK - {name} ({im.size[0]}x{im.size[1]})")
        except Exception as ex:
            imglabel.config(text="(bad image)")
            statusvar.set(f"Error: {ex}")

    if start_path and os.path.exists(start_path):
        root.after(200, lambda: load(start_path))
    if has_dnd:
        def _on_drop(ev):
            import re as _re
            data = (ev.data or "").strip()
            if not data:
                return
            if data.startswith("{"):
                paths = [p.strip().strip("{}") for p in
                         _re.split(r"}\s+{", data)]
            else:
                paths = [data]
            paths = [p for p in paths if p and os.path.exists(p)]
            if paths:
                try:
                    try:
                        _grab = root.grab_current()
                    except Exception:
                        _grab = None
                    if _grab:
                        statusvar.set("Close the open dialog first, "
                                      "then drop again")
                    else:
                        show_batch(paths)  # single file falls through to load()
                except Exception as ex:
                    try:
                        statusvar.set(f"Drop failed: {ex}")
                    except Exception:
                        pass
        try:
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", _on_drop)
        except Exception as ex:
            statusvar.set(f"Drop disabled: {ex}")
    root.after(2500, lambda: check_updates())
    try:
        if _load_settings().get("pinned"):
            toggle_pin(True)
    except Exception:
        pass
    def _restore_cover_state():
        # runs after deiconify (withdrawn window has no real size yet)
        try:
            if _load_settings().get("cover_hidden"):
                toggle_cover(True)
        except Exception:
            pass
    root.after(150, _restore_cover_state)
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        _startup = sys.argv[1]
        root.after(100, lambda: load(_startup))
    # First launch (or installer --first-install): show About (support links).
    _first_install = any(a == "--first-install" for a in sys.argv[1:])
    try:
        _about_done = bool(_load_settings().get("about_shown"))
    except Exception:
        _about_done = False
    if _first_install or not _about_done:
        try:
            _save_settings({"about_shown": True})
        except Exception:
            pass
        root.after(600, lambda: show_about())
    try:
        # show once, already at final size — no white flash / shrink jump
        root.update_idletasks()
        root.deiconify()
        root.update()  # full pump: the first map must complete for a valid HWND
        try:
            # Dark native title bar (Windows 10 20H1+ / 11): same family
            # look as the Avalonia apps. winfo_id() is the Tk client child,
            # so the frame HWND is its parent (verified: FindWindow match).
            # Must run after deiconify (withdrawn window has no HWND).
            # Native frame stays: snap + min/max/close work.
            import ctypes as _ct
            _hwnd = _ct.windll.user32.GetParent(root.winfo_id())
            _dark = _ct.c_int(1)
            # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE (Win11), 19 = older value
            if _ct.windll.dwmapi.DwmSetWindowAttribute(
                    _hwnd, 20, _ct.byref(_dark), _ct.sizeof(_dark)) != 0:
                _ct.windll.dwmapi.DwmSetWindowAttribute(
                    _hwnd, 19, _ct.byref(_dark), _ct.sizeof(_dark))
        except Exception:
            pass
    except Exception:
        pass
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--info":
        print_info(sys.argv[2])
    elif len(sys.argv) >= 3 and sys.argv[1] == "--batch-rename":
        _args = sys.argv[2:]
        _apply = "--apply" in _args
        _rec = "--recursive" in _args
        _inputs = [a for a in _args if not a.startswith("--")]
        if not _inputs:
            print("usage: pkgviewer.py --batch-rename <file|folder> [...] "
                  "[--recursive] [--apply]")
        else:
            print_batch(_inputs, recursive=_rec, apply=_apply)
    elif len(sys.argv) >= 3 and sys.argv[1] == "--revert":
        _args = sys.argv[2:]
        _apply = "--apply" in _args
        _logs = [a for a in _args if not a.startswith("--")]
        import glob as _glob
        _expanded = []
        for _l in _logs:
            _g = _glob.glob(_l) if ("*" in _l or "?" in _l) else [_l]
            _expanded.extend(_g or [_l])
        _logs = _expanded
        if not _logs:
            print("usage: pkgviewer.py --revert <batch_rename_*.log> [--apply]")
        else:
            for _log in _logs:
                _pairs = parse_revert_log(_log)
                if not _pairs:
                    print(f"{_log}: no valid entries (bad log or empty).")
                    continue
                if not _apply:
                    print(f"{_log}: dry run, {len(_pairs)} entries "
                          f"(re-run with --apply to revert):")
                    for _cur, _rst in _pairs:
                        print(f"  [REVERT] {os.path.basename(_cur)}  ->  "
                              f"{os.path.basename(_rst)}")
                    continue
                _rev, _skip = apply_revert(_pairs)
                print(f"{_log}: reverted {len(_rev)}, skipped {len(_skip)}.")
                for _cur, _reason in _skip:
                    print(f"  [SKIP] {os.path.basename(_cur)} ({_reason})")
    elif len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        run_gui(sys.argv[1])
    elif len(sys.argv) >= 2 and sys.argv[1] == "--info":
        print("usage: pkgviewer.py --info <file.pkg>")
    else:
        run_gui()

#!/usr/bin/env python3
"""PKG Viewer - PS4 + PS5 (FIH/CNT). Clean dark UI (tkinter) + CLI --info mode."""
import io
import json
import os
import struct
import sys

CNT_MAGIC = b"\x7fCNT"
FIH_MAGIC = b"\x7fFIH"

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
PS4_CAT_TYPES = {"gd": "Game", "ac": "DLC", "gp": "Update Patch"}


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
        return f"{(top >> 8) & 0xFF}.{top & 0xFF:02X}"
    except Exception:
        return str(v)


def ps4_pkg_type(cat):
    if not cat:
        return "-"
    lab = PS4_CAT_TYPES.get(str(cat).lower())
    return f"{lab} ({cat})" if lab else str(cat)


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
        return parse_app_folder(path)
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        magic = f.read(4)
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
                return {"error": "embedded CNT magic bad"}
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
                    ("Signature", "official" if signed == 0x80 else "debug / fake"),
                    ("Size", fmt_size(size)),
                    ("PFS image", f"{fmt_size(pfs_size)} @ {pfs_off:#x}"),
                    ("Entries", str(len(ents)))]
            rows += extra
            if not any(k == "Content ID" for k, _ in rows):
                rows.insert(2, ("Content ID", cid))
            return {"ok": True, "kind": "ps5", "path": path, "size": size,
                    "title": title or os.path.basename(path),
                    "rows": rows, "entries": ents, "meta": meta, "icon_entry": "icon0.png"}
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
            if sfo and not sfo.get("_error"):
                title = sfo.get("TITLE", "")
                _cid4 = sfo.get("CONTENT_ID", cid)
                _cat4 = sfo.get("CATEGORY", "")
                extra = [("Title ID", sfo.get("TITLE_ID", "")),
                         ("Content ID", _cid4),
                         ("Region", content_region(_cid4)),
                         ("Type", ps4_pkg_type(_cat4)),
                         ("Version", sfo.get("VERSION", "")),
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
                    ("Content ID", sfo.get("CONTENT_ID", cid) if sfo else cid),
                    ("Size", fmt_size(size)),
                    ("Entries", f"{n} ({sc} sys)"),
                    ("Body", f"@ {body_off:#x}")]
            rows += extra
            return {"ok": True, "kind": "ps4", "path": path, "size": size,
                    "title": title or os.path.basename(path),
                    "rows": rows, "entries": ents, "meta": meta or sfo,
                    "icon_entry": "icon0.png"}
        else:
            return {"error": f"unknown magic {magic!r}"}


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
    rows += extra
    ents = []
    if os.path.isfile(icon):
        try:
            ents.append({"id": 0, "name": "icon0.png", "size": os.path.getsize(icon),
                         "abs_off": -1, "local_path": icon})
        except OSError:
            pass
    r = {"ok": True, "kind": "ps5", "path": path, "size": total,
         "title": title or os.path.basename(path.rstrip("/\\")),
         "rows": rows, "entries": ents, "meta": meta, "icon_entry": "icon0.png"}
    if os.path.isfile(icon):
        r["folder_icon"] = icon
    return r


class _Exfat:
    """Minimal read-only exFAT: boot sector, FAT walk, dir scan."""

    def __init__(self, path):
        self.path = path
        self.f = open(path, "rb")
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

    def list_dir(self, first, size, nofat):
        raw = self._iter_dir(first, size, nofat)
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
            i += 32
        return items

    def find(self, parts):
        clus, size, nofat = self.root_clus, 1 << 30, False
        for depth, part in enumerate(parts):
            if depth == 0 and (part == "" or part.lower().endswith(".exfat")):
                continue
            found = None
            for name, attrs, first, sz, nf in self.list_dir(clus, size, nofat):
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


def parse_exfat_image(path):
    """PS5 exFAT game image: pull sce_sys/param.json + icon0.png via FAT walk."""
    size = os.path.getsize(path)
    fs = _Exfat(path)
    try:
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
        root = fs.list_dir(fs.root_clus, 1 << 30, False)
        ntop = len(root)
        rows = [("Platform", "PS5 exFAT image"),
                ("Size", fmt_size(size)),
                ("Root entries", str(ntop))]
        rows += extra
        return {"ok": True, "kind": "ps5", "path": path, "size": size,
                "title": title or os.path.basename(path),
                "rows": rows, "entries": ents, "meta": meta,
                "icon_entry": "icon0.png", "exfat": True}
    finally:
        fs.close()


def read_entry_bytes(path, abs_off, size, limit=32_000_000):
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
        for k in CURATED_SFO:
            if k in meta:
                lines.append(f"{k} = {meta[k]}")
        titles = sorted(k for k in meta if k.startswith("TITLE_"))
        if titles:
            extra = len(titles) - 6
            lines.append(f"(+{len(titles)} localized titles: "
                         f"{', '.join(titles[:6])}{'...' if extra > 0 else ''})")
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
    r = parse_pkg(path)
    if "error" in r and not r.get("ok"):
        print("ERROR:", r["error"]); return
    print("FILE:", os.path.basename(path))
    print("TITLE:", r["title"])
    for k, v in r["rows"]:
        print(f"{k}: {v}")
    print(f"--- entries ({len(r['entries'])}) ---")
    for e in r["entries"]:
        print(f"  id={e['id']} size={e['size']} name={e['name']!r}")


# ---------------- GUI ----------------
BG, CARD, CARD2, ACCENT = "#0f1115", "#1a1e26", "#222836", "#3b82f6"
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
                im = _I.open(p).convert("RGB")
                im.thumbnail(size)
                return im
        return None
    except Exception:
        return None


def run_gui(start_path=None):
    import tkinter as tk
    from tkinter import filedialog, ttk
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
    root.title("PKG Viewer  •  PS4 / PS5")
    root.geometry("1060x700")
    root.configure(bg=BG)
    root.minsize(900, 600)
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
    style.configure("Accent.TButton", background=ACCENT, foreground="white", font=FONT,
                    borderwidth=0, padding=(16, 9))
    style.map("Accent.TButton", background=[("active", "#2f6fe0")])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=CARD, foreground=MUTED, padding=(18, 8), font=FONT)
    style.map("TNotebook.Tab", background=[("selected", CARD2)],
              foreground=[("selected", TEXT)])
    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                    font=FONT, rowheight=26, borderwidth=0)
    style.configure("Treeview.Heading", background=CARD2, foreground=MUTED, font=FONT_SMALL)
    style.map("Treeview", background=[("selected", ACCENT)])
    style.configure("TCombobox", fieldbackground=CARD2, background=CARD2, foreground=TEXT,
                    arrowcolor=MUTED)
    style.configure("Ghost.TButton", background=CARD2, foreground=TEXT, font=FONT,
                    borderwidth=0, padding=(12, 7))
    style.map("Ghost.TButton", background=[("active", "#2c3342")])

    # header: slim toolbar
    header = ttk.Frame(root, padding=(16, 12))
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
    ttk.Button(header, text="Open", style="Accent.TButton",
               command=lambda: pick()).pack(side="left")
    pathvar = tk.StringVar(value="Drop a .pkg / .exfat file or app folder here")
    ttk.Label(header, textvariable=pathvar, font=FONT_SMALL, foreground=MUTED).pack(
        side="left", padx=(14, 0))

    # body
    body = ttk.Frame(root, padding=(16, 4))
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)
    body.rowconfigure(0, weight=1)

    # ---- hero: cover + title/badges (left) ----
    left = ttk.Frame(body, style="Card.TFrame", padding=18)
    left.grid(row=0, column=0, sticky="ns", padx=(0, 14))
    imglabel = tk.Label(left, bg=CARD, fg=MUTED,
                        text="Drop a file or folder here\n\nor click Open",
                        font=FONT_MID, justify="center")
    imglabel.pack(pady=40)
    titlevar = tk.StringVar(value="—")
    tk.Label(left, textvariable=titlevar, bg=CARD, fg=TEXT, font=FONT_BIG,
             wraplength=300, justify="left").pack(pady=(14, 8), anchor="w")
    badgerow = ttk.Frame(left, style="Card.TFrame")
    badgerow.pack(anchor="w", pady=(0, 4))
    badgevars = [tk.StringVar(value="") for _ in range(3)]
    badge_labels = []
    for bv in badgevars:
        lb = tk.Label(badgerow, textvariable=bv, bg=CARD2, fg=TEXT,
                      font=FONT_BADGE, padx=10, pady=4)
        lb.pack(side="left", padx=(0, 8))
        badge_labels.append(lb)
    state["badges"] = badgevars
    state["badge_labels"] = badge_labels
    ttk.Label(left, text="Image:", style="Muted.Card.TLabel").pack(anchor="w", pady=(14, 4))
    imgchoice = ttk.Combobox(left, state="readonly", width=30)
    imgchoice.pack(anchor="w")
    imgchoice.bind("<<ComboboxSelected>>", lambda _e: show_image(imgchoice.get()))
    imgbtns = ttk.Frame(left, style="Card.TFrame")
    imgbtns.pack(anchor="w", pady=(8, 0))
    ttk.Button(imgbtns, text="Save PNG", style="Ghost.TButton",
               command=lambda: save_current_image()).pack(side="left", padx=(0, 6))
    ttk.Button(imgbtns, text="Copy", style="Ghost.TButton",
               command=lambda: copy_current_image()).pack(side="left")

    # right column
    right = ttk.Frame(body)
    right.grid(row=0, column=1, sticky="nsew")
    right.rowconfigure(1, weight=1)
    right.columnconfigure(0, weight=1)

    specbox = ttk.Frame(right, style="Card.TFrame", padding=16)
    specbox.pack(fill="x", pady=(0, 12))
    spec_rows = []
    for _ in range(5):
        row = ttk.Frame(specbox, style="Card.TFrame")
        row.pack(fill="x", pady=3)
        row.columnconfigure(0, weight=1)
        row.columnconfigure(1, weight=1)
        cells = []
        for col in (0, 1):
            cell = ttk.Frame(row, style="Card.TFrame")
            cell.grid(row=0, column=col, sticky="w", padx=(0, 24))
            k = ttk.Label(cell, text="", style="SpecKey.TLabel")
            k.pack(anchor="w")
            v = tk.Entry(cell, bg=CARD, fg=TEXT, font=FONT_MID, relief="flat",
                         readonlybackground=CARD, highlightthickness=0,
                         state="readonly", width=34)
            v.pack(anchor="w")
            cells.append((k, v))
        spec_rows.append(cells)
    state["spec_cells"] = spec_rows

    nb = ttk.Notebook(right)
    nb.pack(fill="both", expand=True)
    tab_entries = ttk.Frame(nb)
    tab_meta = ttk.Frame(nb)
    nb.add(tab_entries, text="  Files  ")
    nb.add(tab_meta, text="  Details  ")

    tree = ttk.Treeview(tab_entries, columns=("id", "size"), show="tree headings")
    tree.heading("#0", text="name", anchor="w")
    tree.heading("id", text="id", anchor="w")
    tree.heading("size", text="size", anchor="e")
    tree.column("#0", width=320)
    tree.column("id", width=70)
    tree.column("size", width=110, anchor="e")
    sb = ttk.Scrollbar(tab_entries, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    tree.pack(side="left", fill="both", expand=True)
    sb.pack(side="left", fill="y")

    metabar = ttk.Frame(tab_meta, style="Card.TFrame")
    metabar.pack(fill="x", pady=(0, 4))
    detailvar = tk.StringVar(value="Show all")
    detailbtn = ttk.Button(metabar, textvariable=detailvar, style="Accent.TButton",
                           command=lambda: toggle_details())
    detailbtn.pack(side="right")
    metatext = tk.Text(tab_meta, bg=CARD, fg=TEXT, font=("Consolas", 9),
                       wrap="none", borderwidth=0, padx=10, pady=10,
                       height=12, selectbackground=ACCENT,
                       selectforeground="white", insertbackground=TEXT)
    metatext.pack(fill="both", expand=True)
    root.bind_all("<KeyPress>", lambda e: _global_ctrl_keys(e, root, statusvar))
    ctxmenu = tk.Menu(root, tearoff=0, bg=CARD, fg=TEXT,
                      activebackground=ACCENT, activeforeground="white")
    ctxmenu.add_command(label="Copy",
                        command=lambda: copy_text_selection(metatext))
    ctxmenu.add_command(label="Select all",
                        command=lambda: select_all_text(metatext))
    metatext.bind("<Button-3>", lambda e: ctxmenu.tk_popup(e.x_root, e.y_root))

    statusvar = tk.StringVar(value="Ready")
    tk.Label(root, textvariable=statusvar, bg=BG, fg=MUTED, font=FONT_SMALL,
             anchor="w", padx=12, pady=6).pack(fill="x", side="bottom")

    # logic
    def pick():
        p = filedialog.askopenfilename(title="Select PKG / image file",
                                       filetypes=[("Game files", "*.pkg *.exfat *.ffpfsc"),
                                                  ("PKG", "*.pkg"),
                                                  ("exFAT image", "*.exfat"),
                                                  ("all", "*.*")])
        if p:
            load(p)
        else:
            d = filedialog.askdirectory(title="...or select an app folder")
            if d:
                load(d)

    def load(p):
        statusvar.set("Reading...")
        root.update_idletasks()
        try:
            r = parse_pkg(p)
        except Exception as e:
            statusvar.set(f"Error: {e}")
            return
        if not r.get("ok"):
            statusvar.set("Error: " + r.get("error", "?"))
            return
        state["result"] = r
        state["show_all"] = False
        detailvar.set("Show all")
        pathvar.set(os.path.basename(p))
        titlevar.set(r["title"])
        plat = r["rows"][0][1] if r["rows"] else ""
        _rd = dict(r["rows"])
        badges = state.get("badges", [])
        _blabs = state.get("badge_labels", [])
        _bvals = [plat,
                  _rd.get("Region", ""),
                  f"{fmt_size(r['size'])}"]
        _bcolors = ["#3b82f6" if "PS5" in plat else "#22c55e",
                    "#22c55e", "#6b7280"]
        for bv, val, lb, col in zip(badges, _bvals, _blabs, _bcolors):
            bv.set(val or "")
            try:
                lb.config(bg=col)
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
        for e in r["entries"]:
            if not e["name"]:
                continue
            tree.insert("", "end", text=e["name"], values=(e["id"], fmt_size(e["size"])))
        metatext.delete("1.0", "end")
        refresh_details()
        # image choices: png entries
        pngs = [e["name"] for e in r["entries"]
                if e["name"].lower().endswith(".png") and e["size"] > 0]
        imgchoice["values"] = pngs
        if pngs:
            first = "icon0.png" if "icon0.png" in pngs else pngs[0]
            imgchoice.set(first)
            show_image(first)
        else:
            imgchoice.set("")
            imglabel.config(image="", text="(no image)")
        statusvar.set(f"OK - {len(r['entries'])} entries")

    def refresh_details():
        r = state.get("result")
        metatext.delete("1.0", "end")
        if not r:
            return
        if state.get("show_all"):
            lines = full_meta_lines(r.get("meta"))
        else:
            lines = curated_meta_lines(r.get("kind"), r.get("meta"))
        metatext.insert("end", "\n".join(lines) + ("\n" if lines else ""))

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
        if not e:
            return
        data = read_entry_bytes(r["path"], e["abs_off"], e["size"])
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            statusvar.set("Not a PNG")
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
            im.thumbnail((360, 360))
            ph = ImageTk.PhotoImage(im)
            state["photo"] = ph
            imglabel.config(image=ph, text="")
            imglabel.image = ph
            statusvar.set(f"OK - {name} ({im.size[0]}x{im.size[1]})")
        except Exception as ex:
            imglabel.config(text="(bad image)")
            statusvar.set(f"Error: {ex}")

    if start_path and os.path.exists(start_path):
        root.after(200, lambda: load(start_path))
    if has_dnd:
        def _on_drop(ev):
            p = (ev.data or "").strip().strip("{}").split("} {")[0]
            if p and os.path.exists(p):
                load(p)
        try:
            root.drop_target_register(DND_FILES)
            root.dnd_bind("<<Drop>>", _on_drop)
        except Exception as ex:
            statusvar.set(f"Drop disabled: {ex}")
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--info":
        print_info(sys.argv[2])
    elif len(sys.argv) >= 2 and os.path.exists(sys.argv[1]):
        run_gui(sys.argv[1])
    elif len(sys.argv) >= 2 and sys.argv[1] == "--info":
        print("usage: pkgviewer.py --info <file.pkg>")
    else:
        run_gui()

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


def _param_json_meta(meta):
    lp = meta.get("localizedParameters", {})
    lang = lp.get("defaultLanguage", "en-US")
    title = (lp.get(lang) or {}).get("titleName", "")
    extra = [("Title ID", meta.get("titleId", "")),
             ("Content ID", meta.get("contentId", "")),
             ("Content Ver", meta.get("contentVersion", "")),
             ("Master Ver", meta.get("masterVersion", ""))]
    sv = meta.get("sdkVersion")
    rv = meta.get("requiredSystemSoftwareVersion")
    extra.append(("SDK", hex(sv) if isinstance(sv, int) else str(sv or "")))
    extra.append(("Req. FW", hex(rv) if isinstance(rv, int) else str(rv or "")))
    return title, extra


def parse_pkg(path):
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        magic = f.read(4)
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
                    ("Content ID", cid),
                    ("Size", fmt_size(size)),
                    ("PFS image", f"{fmt_size(pfs_size)} @ {pfs_off:#x}"),
                    ("Entries", str(len(ents)))]
            rows += extra
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
                extra = [("Title ID", sfo.get("TITLE_ID", "")),
                         ("Category", sfo.get("CATEGORY", "")),
                         ("Version", sfo.get("VERSION", "")),
                         ("Content ID", sfo.get("CONTENT_ID", cid))]
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


def read_entry_bytes(path, abs_off, size, limit=32_000_000):
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
CURATED_JSON = ["titleId", "contentId", "contentVersion", "masterVersion",
                "sdkVersion", "requiredSystemSoftwareVersion"]


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
            lines.append(f"titleName [{lang}] = {t}")
        for k in CURATED_JSON:
            if k in meta:
                v = meta[k]
                if isinstance(v, int):
                    v = hex(v)
                lines.append(f"{k} = {v}")
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
BG, CARD, ACCENT = "#16181d", "#20242c", "#2d6cdf"
TEXT, MUTED = "#eef0f5", "#9aa3b2"
FONT = ("Segoe UI", 10)
FONT_BIG = ("Segoe UI", 14, "bold")
FONT_SMALL = ("Segoe UI", 9)


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

    root = tk.Tk()
    root.title("PKG Viewer  •  PS4 / PS5")
    root.geometry("960x640")
    root.configure(bg=BG)
    root.minsize(820, 540)

    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:
        pass
    style.configure("TFrame", background=BG)
    style.configure("Card.TFrame", background=CARD)
    style.configure("TLabel", background=BG, foreground=TEXT, font=FONT)
    style.configure("Card.TLabel", background=CARD, foreground=TEXT, font=FONT)
    style.configure("Muted.Card.TLabel", background=CARD, foreground=MUTED, font=FONT_SMALL)
    style.configure("Title.Card.TLabel", background=CARD, foreground=TEXT, font=FONT_BIG)
    style.configure("Accent.TButton", background=ACCENT, foreground="white", font=FONT,
                    borderwidth=0, padding=(14, 8))
    style.map("Accent.TButton", background=[("active", "#3d7bef")])
    style.configure("TNotebook", background=BG, borderwidth=0)
    style.configure("TNotebook.Tab", background=CARD, foreground=TEXT, padding=(14, 6), font=FONT)
    style.map("TNotebook.Tab", background=[("selected", ACCENT)])
    style.configure("Treeview", background=CARD, fieldbackground=CARD, foreground=TEXT,
                    font=FONT_SMALL, rowheight=24, borderwidth=0)
    style.configure("Treeview.Heading", background="#2a303b", foreground=TEXT, font=FONT_SMALL)
    style.map("Treeview", background=[("selected", ACCENT)])
    style.configure("TCombobox", fieldbackground=CARD, background=CARD, foreground=TEXT)
    style.configure("Ghost.TButton", background=CARD, foreground=MUTED, font=FONT_SMALL,
                    borderwidth=0, padding=(10, 5))
    style.map("Ghost.TButton", background=[("active", "#2a303b")], foreground=[("active", TEXT)])

    # header
    header = ttk.Frame(root, padding=(12, 10))
    header.pack(fill="x")
    ttk.Button(header, text="Open PKG", style="Accent.TButton",
               command=lambda: pick()).pack(side="left")
    pathvar = tk.StringVar(value="Select a PKG file...")
    ttk.Label(header, textvariable=pathvar, font=FONT_SMALL, foreground=MUTED).pack(
        side="left", padx=(12, 0))

    # body
    body = ttk.Frame(root, padding=(12, 0))
    body.pack(fill="both", expand=True)
    body.columnconfigure(1, weight=1)
    body.rowconfigure(0, weight=1)

    # left card
    left = ttk.Frame(body, style="Card.TFrame", padding=14)
    left.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
    imglabel = tk.Label(left, bg=CARD, fg=MUTED, text="(icon)",
                        font=FONT_SMALL)
    imglabel.pack()
    titlevar = tk.StringVar(value="—")
    tk.Label(left, textvariable=titlevar, bg=CARD, fg=TEXT, font=FONT_BIG,
             wraplength=300, justify="left").pack(pady=(12, 2), anchor="w")
    badgevar = tk.StringVar(value="")
    tk.Label(left, textvariable=badgevar, bg=CARD, fg=MUTED,
             font=FONT_SMALL).pack(anchor="w")
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

    specbox = ttk.Frame(right, style="Card.TFrame", padding=12)
    specbox.pack(fill="x", pady=(0, 10))
    spec_rows = []
    for _ in range(8):
        k = ttk.Label(specbox, text="", style="Muted.Card.TLabel", width=14)
        v = tk.Entry(specbox, bg=CARD, fg=TEXT, font=FONT, relief="flat",
                     readonlybackground=CARD, highlightthickness=0,
                     state="readonly", width=60)
        k.grid(column=0, row=len(spec_rows), sticky="w", pady=2)
        v.grid(column=1, row=len(spec_rows), sticky="we", padx=(8, 0), pady=2)
        spec_rows.append((k, v))
    specbox.columnconfigure(1, weight=1)

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
        p = filedialog.askopenfilename(title="Select PKG file",
                                       filetypes=[("PKG", "*.pkg"), ("all", "*.*")])
        if p:
            load(p)

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
        pathvar.set(p)
        titlevar.set(r["title"])
        plat = r["rows"][0][1] if r["rows"] else ""
        badgevar.set(f"{plat}  •  {fmt_size(r['size'])}")
        for (k, v), (kl, vl) in zip(r["rows"][:8], spec_rows):
            kl.config(text=k)
            vl.config(state="normal")
            vl.delete(0, "end")
            vl.insert(0, str(v)[:90])
            vl.config(state="readonly")
        for kl, vl in spec_rows[len(r["rows"]):]:
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
            im.thumbnail((300, 300))
            ph = ImageTk.PhotoImage(im)
            state["photo"] = ph
            imglabel.config(image=ph, text="")
            imglabel.image = ph
            statusvar.set(f"OK - {name} ({im.size[0]}x{im.size[1]})")
        except Exception as ex:
            imglabel.config(text="(bad image)")
            statusvar.set(f"Error: {ex}")

    if start_path and os.path.isfile(start_path):
        root.after(200, lambda: load(start_path))
    root.mainloop()


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--info":
        print_info(sys.argv[2])
    elif len(sys.argv) >= 2 and os.path.isfile(sys.argv[1]):
        run_gui(sys.argv[1])
    elif len(sys.argv) >= 2 and sys.argv[1] == "--info":
        print("usage: pkgviewer.py --info <file.pkg>")
    else:
        run_gui()

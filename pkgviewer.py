#!/usr/bin/env python3
"""PKG Viewer - PS4 + PS5 (FIH/CNT). Clean dark UI (tkinter) + CLI --info mode."""
import io
import json
import os
import struct
import sys

APP_VERSION = "v1.7.5"  # bump on every release — the updater compares this
UPDATE_REPO = "Loopayeh/pkg-viewer"
UPDATE_EXE = "PKGViewer.exe"

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
        return f"{(top >> 8) & 0xFF:X}.{top & 0xFF:02X}"
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
                    "icon_entry": "icon0.png",
                    "patch_tid": sfo.get("TITLE_ID", "") if isinstance(sfo, dict) else "",
                    "own_ver": sfo.get("VERSION", "") if isinstance(sfo, dict) else ""}
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
    return parse_ps5_retail_stub(path, size, hdr)


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


def fetch_store_cover(cid):
    """(name, cover_url, release, tagline) from PlayStation Store. Square MASTER art preferred."""
    import re as _re
    import urllib.request as _ureq
    if not cid or "-" not in cid:
        return None, None, None, None
    if cid in _STORE_CACHE:
        return _STORE_CACHE[cid]
    loc = _STORE_LOCALE.get(cid.split("-")[0][:2].upper(), "en-us")
    url = "https://store.playstation.com/%s/product/%s" % (loc, cid)
    try:
        req = _ureq.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=20) as r:
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
    try:
        req = _ureq.Request(host + "/" + tid, headers={"User-Agent": "Mozilla/5.0"})
        with _ureq.urlopen(req, timeout=20) as r:
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
        with _ureq.urlopen(req2, timeout=20) as r2:
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
        """List dir entries; if want is set, stop early once found (faster)."""
        if nofat:
            self.f.seek(self._clus_off(first))
            raw = self.f.read(min(size, 1 << 20))
            return self._parse_dir(raw, want)
        out = bytearray()
        clus = first
        while clus is not None and len(out) < size:
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
    finally:
        try:
            img.close()
        except Exception:
            pass
    rows = [("Platform", "PS5 ffpkg image"),
            ("Size", fmt_size(size))] + extra
    return {"ok": True, "kind": "ps5", "path": path, "size": size,
            "title": title or os.path.basename(path),
            "rows": rows, "entries": ents, "meta": meta,
            "icon_entry": "icon0.png", "ffpkg": True}


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
    rows = [("Platform", platform),
            ("Size", fmt_size(size))]
    if inner_name:
        rows.append(("Inner file", inner_name))
    rows += extra
    return {"ok": True, "kind": "ps5", "path": path, "size": size,
            "title": title or os.path.basename(path),
            "rows": rows, "entries": ents, "meta": meta,
            "icon_entry": "icon0.png", "exfat": True}


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
                im = _I.open(p).convert("RGB")
                im.thumbnail(size)
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
    root.title("PKG Viewer %s  •  PS3 / PS4 / PS5  •  by Loopayeh" % APP_VERSION)
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
    style.configure("Accent.TButton", background=ACCENT, foreground="#171717", font=FONT,
                    borderwidth=0, padding=(16, 9))
    style.map("Accent.TButton", background=[("active", "#6fa8ff")])
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
    updatebtn = ttk.Button(header, text="Check updates", style="Ghost.TButton",
                           command=lambda: check_updates(manual=True))
    updatebtn.pack(side="right")
    ttk.Button(header, text="About", style="Ghost.TButton",
               command=lambda: show_about()).pack(side="right", padx=(0, 8))
    pathvar = tk.StringVar(value="Drop a .pkg / .exfat / .ffpfsc / .ffpkg file or app folder here")
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
    imgframe = tk.Frame(left, bg=CARD, width=400, height=400)
    imgframe.pack(pady=(6, 0))
    imgframe.pack_propagate(False)
    imglabel = tk.Label(imgframe, bg=CARD, fg=MUTED,
                        text="Drop a file or folder here\n\nor click Open",
                        font=FONT_MID, justify="center")
    imglabel.place(relx=0.5, rely=0.5, anchor="center")
    titlevar = tk.StringVar(value="—")
    tk.Label(left, textvariable=titlevar, bg=CARD, fg=TEXT, font=(FONT[0], 13, "bold"),
             wraplength=380, justify="left").pack(pady=(6, 4), anchor="w")
    badgerow = ttk.Frame(left, style="Card.TFrame")
    badgerow.pack(anchor="w", pady=(0, 2))
    badgevars = [tk.StringVar(value="") for _ in range(4)]
    badge_labels = []
    for bv in badgevars:
        lb = tk.Label(badgerow, textvariable=bv, bg=CARD2, fg="#171717",
                      font=FONT_BADGE, padx=8, pady=3)
        lb.pack(side="left", padx=(0, 6), pady=2)
        badge_labels.append(lb)
    state["badges"] = badgevars
    state["badge_labels"] = badge_labels
    imgrow = ttk.Frame(left, style="Card.TFrame")
    imgrow.pack(anchor="w", pady=(6, 0))
    ttk.Label(imgrow, text="Image:", style="Muted.Card.TLabel").pack(side="left")
    state["imgcount"] = tk.StringVar(value="")
    tk.Label(imgrow, textvariable=state["imgcount"], bg=CARD, fg=MUTED,
             font=FONT_SMALL).pack(side="left", padx=(6, 0))
    imgchoice = ttk.Combobox(left, state="readonly", width=24)
    imgchoice.pack(anchor="w", pady=(2, 0))
    imgchoice.bind("<<ComboboxSelected>>", lambda _e: show_image(imgchoice.get()))
    def _step_image(d):
        vals = list(imgchoice["values"])
        if not vals:
            return
        try:
            i = vals.index(imgchoice.get())
        except ValueError:
            i = 0
        i = (i + d) % len(vals)
        imgchoice.set(vals[i])
        show_image(vals[i])
    imgnav = ttk.Frame(left, style="Card.TFrame")
    imgnav.pack(anchor="w", pady=(6, 0))
    ttk.Button(imgnav, text="< Prev", style="Ghost.TButton",
               command=lambda: _step_image(-1)).pack(side="left", padx=(0, 6))
    ttk.Button(imgnav, text="Next >", style="Ghost.TButton",
               command=lambda: _step_image(1)).pack(side="left", padx=(0, 6))
    ttk.Button(imgnav, text="Save", style="Ghost.TButton",
               command=lambda: save_current_image()).pack(side="left", padx=(0, 6))
    ttk.Button(imgnav, text="Copy", style="Ghost.TButton",
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
    nb.add(tab_meta, text="  Details  ")
    nb.add(tab_entries, text="  Files  ")

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
                       selectforeground="#171717", insertbackground=TEXT)
    metatext.pack(fill="both", expand=True)
    root.bind_all("<KeyPress>", lambda e: _global_ctrl_keys(e, root, statusvar))
    ctxmenu = tk.Menu(root, tearoff=0, bg=CARD, fg=TEXT,
                      activebackground=ACCENT, activeforeground="#171717")
    ctxmenu.add_command(label="Copy",
                        command=lambda: copy_text_selection(metatext))
    ctxmenu.add_command(label="Select all",
                        command=lambda: select_all_text(metatext))
    metatext.bind("<Button-3>", lambda e: ctxmenu.tk_popup(e.x_root, e.y_root))

    bottombar = ttk.Frame(root)
    bottombar.pack(fill="x", side="bottom")
    statusvar = tk.StringVar(value="Ready")
    _status_lbl = tk.Label(bottombar, textvariable=statusvar, bg=BG, fg=MUTED,
                           font=FONT_SMALL, anchor="w", justify="left",
                           padx=12, pady=6)
    _status_lbl.pack(side="left", fill="x", expand=True)
    # wrap status text on narrow windows instead of clipping it
    bottombar.bind("<Configure>",
                   lambda e: _status_lbl.config(wraplength=max(200, e.width - 24)))

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
        tk.Label(_ab, text="PKG Viewer %s" % APP_VERSION,
                 bg=CARD, fg=TEXT, font=FONT).pack(padx=36, pady=(20, 0))
        tk.Label(_ab, text="by Loopayeh",
                 bg=CARD, fg=MUTED, font=FONT_SMALL).pack(pady=(2, 0))
        tk.Label(_ab, text="View PS3 / PS4 / PS5 package info and cover art.",
                 bg=CARD, fg=TEXT, font=FONT_SMALL).pack(padx=36,
                                                         pady=(12, 0))
        _links = ttk.Frame(_ab, style="Card.TFrame")
        _links.pack(pady=(14, 0))
        ttk.Button(_links, text="Links", style="Ghost.TButton",
                   command=lambda: _wb.open(
                       "https://loopayeh.github.io/")).pack(side="left")
        ttk.Button(_ab, text="Close", style="Accent.TButton",
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
        try:
            _has_setup = _up.pick_setup_asset(info) is not None
            _portable = not _up.is_installed()
        except Exception:
            _has_setup, _portable = False, False
        if _has_setup and _portable:
            tk.Label(dlg, text="Tip: the installer version is recommended — "
                               "own icon per format, double-click to open, "
                               "silent self-updates.",
                     bg=BG, fg="#4F8EF7", font=FONT_SMALL,
                     wraplength=460, justify="left").pack(anchor="w",
                                                          padx=16, pady=(6, 0))
        _body = (info.get("body", "") or "").strip().split("\n")
        _notes = "\n".join(_body[:12])
        if _notes:
            _tx = tk.Text(dlg, bg=CARD, fg=TEXT, font=FONT_SMALL,
                          wrap="word", borderwidth=0, padx=10, pady=10,
                          height=8, width=60)
            _tx.pack(fill="both", expand=True, padx=16, pady=(10, 0))
            _tx.insert("end", _notes)
            _tx.config(state="disabled")
        _prog = tk.StringVar(value="")
        tk.Label(dlg, textvariable=_prog, bg=BG, fg=MUTED,
                 font=FONT_SMALL).pack(anchor="w", padx=16, pady=(6, 0))
        _btns = tk.Frame(dlg, bg=BG)
        _btns.pack(fill="x", padx=16, pady=14)

        def _dl(prefer_setup=False):
            try:
                _installed = _up.is_installed()
            except Exception:
                _installed = False
            if prefer_setup:
                _installed = True
            _asset = (_up.pick_setup_asset(info) if _installed
                      else _up.pick_exe_asset(info, (UPDATE_EXE,)))
            if not _asset:
                _prog.set("No installer found in this release"
                          if _installed else "No .exe found in this release")
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
                        if _installed:
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
                        elif _up.stage_and_restart(_dest):
                            try:
                                dlg.destroy()
                            except Exception:
                                pass
                            root.after(300, root.destroy)
                        else:
                            _prog.set("Saved to %s (dev mode)" % _dest)
                    except Exception as e:
                        _prog.set("Update failed: %s" % e)
                root.after(0, _fin)
            import threading as _th
            _th.Thread(target=_work, daemon=True).start()
        if _has_setup and _portable:
            ttk.Button(_btns, text="Switch to Installer Version",
                       style="Accent.TButton",
                       command=lambda: _dl(prefer_setup=True)).pack(side="left")
            ttk.Button(_btns, text="Portable instead", style="Ghost.TButton",
                       command=_dl).pack(side="left", padx=(8, 0))
            ttk.Button(_btns, text="Later", style="Ghost.TButton",
                       command=dlg.destroy).pack(side="left", padx=(8, 0))
        else:
            ttk.Button(_btns, text="Download + Restart",
                       style="Accent.TButton", command=_dl).pack(side="left")
            ttk.Button(_btns, text="Later", style="Ghost.TButton",
                       command=dlg.destroy).pack(side="left", padx=(8, 0))

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
        _type = _rd.get("Type", "")
        _has_lz4 = "LZ4" in _rd.get("Assets", "")
        _b0 = "LZ4" if _has_lz4 else plat
        _bvals = [_b0,
                  _rd.get("Region", ""),
                  f"{fmt_size(r['size'])}",
                  _type]
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
            _plat_col = "#8fd694"
        elif "ps5" in _pl:
            _plat_col = "#91c8f6"
        else:
            _plat_col = "#6b7280"
        _tl = _type.lower()
        _type_col = ("#5fa8ff" if "update" in _tl
                     else "#f59e5b" if ("dlc" in _tl or "patch" in _tl)
                     else "#10b981" if _type else "#6b7280")
        _bcolors = [_plat_col, "#e17b7b", "#6b7280", _type_col]
        for bv, val, lb, col in zip(badges, _bvals, _blabs, _bcolors):
            bv.set(val or "")
            try:
                lb.config(bg=col, fg="#171717")
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
            tree.insert("", "end", text=e["name"],
                        values=(e["id"], fmt_size(e["size"]), e.get("codec", "")))
        metatext.delete("1.0", "end")
        refresh_details()
        # image choices: png entries
        pngs = [e["name"] for e in r["entries"]
                if e["name"].lower().endswith(".png") and e["size"] > 0]
        imgchoice["values"] = pngs
        try:
            state["imgcount"].set(f"{len(pngs)} images" if len(pngs) != 1 else "1 image")
        except Exception:
            pass
        if pngs:
            first = "icon0.png" if "icon0.png" in pngs else pngs[0]
            imgchoice.set(first)
            show_image(first)
        elif r.get("store_cid"):
            imgchoice.set("")
            imglabel.config(image="", text="Fetching cover...")
            try:
                state["imgcount"].set("1 online image")
            except Exception:
                pass
            fetch_store_async(r["store_cid"])
        else:
            imgchoice.set("")
            imglabel.config(image="", text="(no image)")
        if r.get("patch_tid"):
            fetch_patch_async(r["patch_tid"], r.get("own_ver", ""))
        _set_status(f"OK - {len(r['entries'])} entries")

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
            im.thumbnail((380, 380))
            canvas = Image.new("RGB", (400, 400), CARD)
            canvas.paste(im, ((400 - im.size[0]) // 2,
                              (400 - im.size[1]) // 2))
            ph = ImageTk.PhotoImage(canvas)
            state["photo"] = ph
            imglabel.config(image=ph, text="")
            imglabel.image = ph
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
            statusvar.set("OK - store cover not found")
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
            try:
                imgchoice["values"] = ["cover.jpg"]
                imgchoice.set("cover.jpg")
            except Exception:
                pass
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
            im.thumbnail((380, 380))
            # fixed-size canvas: pad with card bg so layout never shifts
            canvas = Image.new("RGB", (400, 400), CARD)
            canvas.paste(im, ((400 - im.size[0]) // 2,
                              (400 - im.size[1]) // 2))
            ph = ImageTk.PhotoImage(canvas)
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
    root.after(2500, lambda: check_updates())
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        _startup = sys.argv[1]
        root.after(100, lambda: load(_startup))
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

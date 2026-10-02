"""Full PS4 PKG extract + build via LibOrbisPkg (same engine as PkgEditor).

Uses the LibOrbisPkg.dll shipped with PkgEditor installs through pythonnet:
  extract_full(pkg, outdir)  -> decrypts inner PFS, writes all files + .gp4
  build_from_gp4(gp4, out)   -> rebuilds a fake PKG from a .gp4 project

Passcode: 32 zeros (standard for FPKG). Retail PKGs need their real passcode.
"""
import os

_DLL_CANDIDATES = [
    r"D:\Tools\PkgEditor-0.3.1\LibOrbisPkg.dll",
    r"D:\Hermes\tools\PkgEditor-0.2.231\LibOrbisPkg.dll",
]

_LOADED = {"ok": False, "err": "", "dll": ""}


def find_dll():
    for p in _DLL_CANDIDATES:
        if os.path.isfile(p):
            return p
    here = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "LibOrbisPkg.dll")
    if os.path.isfile(here):
        return here
    return ""


def _ensure():
    if _LOADED["ok"]:
        return ""
    try:
        from pythonnet import load
        load()
        import clr
        dll = find_dll()
        if not dll:
            return "LibOrbisPkg.dll not found (install PkgEditor-0.3.1 in D:\\Tools)"
        clr.AddReference(dll)
        _LOADED.update(ok=True, dll=dll)
        return ""
    except Exception as e:
        _LOADED["err"] = str(e)
        return str(e)


def extract_full(pkg_path, out_dir, passcode=None, log=None):
    """Extract ALL files (decrypted PFS) + write .gp4 project. Returns gp4 path."""
    err = _ensure()
    if err:
        raise RuntimeError(err)
    import clr  # noqa: F401
    from LibOrbisPkg.GP4 import Gp4Creator
    os.makedirs(out_dir, exist_ok=True)
    if log:
        log("extracting %s ..." % os.path.basename(pkg_path))
    Gp4Creator.CreateProjectFromPKG(out_dir, pkg_path,
                                    passcode or "0" * 32)
    gp4s = [f for f in os.listdir(out_dir) if f.lower().endswith(".gp4")]
    if log:
        log("done -> %s (%d gp4)" % (out_dir, len(gp4s)))
    if not gp4s:
        return ""
    gp4s.sort()
    return os.path.join(out_dir, gp4s[0])


def _gp4_project_category(gp4_path):
    """Read CATEGORY from the project's param.sfo (sce_sys/param.sfo
    next to the gp4). Returns e.g. 'gp' for patches, '' if unknown."""
    try:
        import struct
        sfo = os.path.join(os.path.dirname(gp4_path), "sce_sys", "param.sfo")
        with open(sfo, "rb") as f:
            d = f.read(4096)
        if d[:4] != b"\x00PSF":
            return ""
        key_off, val_off, count = struct.unpack_from("<III", d, 8)
        for i in range(count):
            ke, kf, vf, vl, vo = struct.unpack_from("<HHIII", d, 20 + i * 16)
            k = d[key_off + ke:].split(b"\x00")[0].decode()
            if k == "CATEGORY":
                return d[val_off + vo:].split(b"\x00")[0].decode()
    except Exception:
        pass
    return ""


def _sanitize_gp4_for_build(gp4_path, log=None):
    """Work around LibOrbisPkg bug 'Playgo Chunk hash file was not
    allocated enough space': a stale sce_sys/app/playgo-chunk.dat entry
    or the <chunk_info> layout breaks PkgBuilder. Returns a temp gp4
    path (same folder) without those, or the original path if nothing
    to strip. The user's file is never modified."""
    try:
        import xml.etree.ElementTree as ET
        tree = ET.parse(gp4_path)
        root = tree.getroot()
        removed = []
        for files in root.iter("files"):
            for f in list(files):
                tp = (f.get("targ_path") or "").replace("\\", "/").lower()
                if tp == "sce_sys/app/playgo-chunk.dat":
                    files.remove(f)
                    removed.append("playgo-chunk.dat entry")
        for vol in root.iter("volume"):
            for ci in list(vol):
                if ci.tag == "chunk_info":
                    vol.remove(ci)
                    removed.append("<chunk_info>")
        # Patches (CATEGORY=gp) extracted as pkg_ps4_app hit the playgo
        # hash bug; rebuild them as pkg_ps4_patch instead.
        if _gp4_project_category(gp4_path) == "gp":
            for vt in root.iter("volume_type"):
                if (vt.text or "").strip() == "pkg_ps4_app":
                    vt.text = "pkg_ps4_patch"
                    removed.append("volume_type->patch")
        if not removed:
            return gp4_path, None
        base, ext = os.path.splitext(gp4_path)
        fixed = base + "_buildfix" + (ext or ".gp4")
        tree.write(fixed, xml_declaration=True, encoding="utf-8")
        if log:
            log("stripped %s (LibOrbisPkg bug)" % ", ".join(removed))
        return fixed, fixed
    except Exception as e:
        if log:
            log("gp4 sanitize skipped: %s" % e)
        return gp4_path, None


def build_from_gp4(gp4_path, out_pkg, log=None):
    """Rebuild a fake PKG from a .gp4 project file. Returns out_pkg."""
    err = _ensure()
    if err:
        raise RuntimeError(err)
    import clr  # noqa: F401
    from System import Action
    from System.IO import File
    from LibOrbisPkg.GP4 import Gp4Project
    from LibOrbisPkg.PKG import PkgProperties, PkgBuilder
    if log:
        log("reading %s ..." % os.path.basename(gp4_path))
    gp4_eff, gp4_tmp = _sanitize_gp4_for_build(gp4_path, log=log)
    with open(gp4_eff, "rb") as f:
        stream = File.OpenRead(gp4_eff)
        try:
            proj = Gp4Project.ReadFrom(stream)
        finally:
            stream.Close()
    props = PkgProperties.FromGp4(proj, os.path.dirname(gp4_path))
    builder = PkgBuilder(props)
    if log:
        log("building %s ..." % os.path.basename(out_pkg))

        def _cb(msg):
            try:
                log(str(msg))
            except Exception:
                pass
        builder.Write(out_pkg, Action[str](_cb))
    else:
        builder.Write(out_pkg, None)
    if log:
        log("done -> %s" % out_pkg)
    if gp4_tmp:
        try:
            os.remove(gp4_tmp)
        except Exception:
            pass
    return out_pkg


def _count_files(d):
    n = 0
    try:
        for _dp, _dn, fns in os.walk(d):
            n += len(fns)
    except Exception:
        pass
    return n


def main(argv):
    """Worker CLI for the GUI progress dialog. Lines on stdout:
    LOG <text>  = status line,  FILES <n> = files so far,
    RESULT <path> = success,  ERROR <text> = failure."""
    import sys
    import threading
    import time

    def out(line):
        try:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            pass

    if len(argv) < 2:
        out("ERROR usage: orbis_full.py extract|build ...")
        return 2
    mode = argv[1].lower()
    try:
        if mode == "extract":
            pkg, dest = argv[2], argv[3]
            code = argv[4] if len(argv) > 4 else "0" * 32
            os.makedirs(dest, exist_ok=True)
            done = {"flag": False, "err": "", "gp4": ""}
            out("LOG decrypting PFS, extracting files...")

            def _poll():
                while not done["flag"]:
                    time.sleep(0.5)
                    out("FILES %d" % _count_files(dest))

            threading.Thread(target=_poll, daemon=True).start()
            try:
                gp4 = extract_full(pkg, dest, code, log=lambda m: out("LOG " + m))
                done["gp4"] = gp4
            except Exception as e:
                done["err"] = str(e)
            done["flag"] = True
            if done["err"]:
                out("ERROR " + done["err"])
                return 1
            out("FILES %d" % _count_files(dest))
            out("RESULT " + (done["gp4"] or dest))
            return 0
        elif mode == "build":
            gp4, dest = argv[2], argv[3]
            out("LOG reading project...")
            try:
                build_from_gp4(gp4, dest, log=lambda m: out("LOG " + m))
            except Exception as e:
                out("ERROR " + str(e))
                return 1
            out("RESULT " + dest)
            return 0
        else:
            out("ERROR unknown mode " + mode)
            return 2
    except Exception as e:
        out("ERROR " + str(e))
        return 1


if __name__ == "__main__":
    import sys as _sys
    _sys.exit(main(_sys.argv))

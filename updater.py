"""Self-update helper for the Hermes game tools (stdlib only, no deps).

Flow:
  1. check_in_background() reads the latest GitHub release in a thread.
  2. The app compares the tag with its own APP_VERSION via is_newer().
  3. On "Download + Restart", the new .exe is downloaded to a temp dir and
     stage_and_restart() swaps it in via a small .bat (Windows cannot
     overwrite a running exe directly) and relaunches it.

Nothing here touches tkinter, so it is safe to use from any thread; the
app must marshal UI work back with root.after().
"""
import json as _json
import os as _os
import subprocess as _subprocess
import sys as _sys
import threading as _threading
import urllib.error as _urlerror  # noqa: F401 (kept for future retries)
import urllib.request as _ureq


def parse_version(s):
    """'v1.6.1' -> (1, 6, 1). Non-numeric parts count as 0."""
    s = (s or "").strip()
    if s[:1].lower() == "v":
        s = s[1:]
    out = []
    for p in s.split("."):
        d = ""
        for ch in p:
            if ch.isdigit():
                d += ch
            else:
                break
        out.append(int(d) if d else 0)
    return tuple(out) or (0,)


def is_newer(latest_tag, current):
    """True if latest_tag is a strictly newer version than current."""
    a = parse_version(latest_tag)
    b = parse_version(current)
    n = max(len(a), len(b))
    a += (0,) * (n - len(a))
    b += (0,) * (n - len(b))
    return a > b


def fetch_latest(repo, timeout=12):
    """Return the latest release dict, or None (no release / private repo /
    no network). Never raises. Keys: tag, name, body, assets[{name,url,size}].
    """
    url = _os.environ.get("PKGVIEWER_UPDATE_API") or \
        "https://api.github.com/repos/%s/releases/latest" % repo
    req = _ureq.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "%s updater" % repo,
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with _ureq.urlopen(req, timeout=timeout) as r:
            data = _json.loads(r.read().decode("utf-8", "replace"))
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("tag_name"):
        return None
    assets = []
    for a in data.get("assets") or []:
        if isinstance(a, dict) and a.get("browser_download_url"):
            assets.append({"name": a.get("name", ""),
                           "url": a["browser_download_url"],
                           "size": a.get("size", 0) or 0})
    return {"tag": data.get("tag_name", ""),
            "name": data.get("name", "") or data.get("tag_name", ""),
            "body": data.get("body", "") or "",
            "assets": assets}


def check_in_background(repo, callback):
    """Fetch the latest release in a daemon thread, then call
    callback(release_or_None). callback runs in the worker thread."""
    def _work():
        try:
            info = fetch_latest(repo)
        except Exception:
            info = None
        try:
            callback(info)
        except Exception:
            pass
    _threading.Thread(target=_work, daemon=True).start()


def pick_exe_asset(info, exe_names=()):
    """Legacy: best portable .exe (exact name first, else first .exe)."""
    assets = [a for a in (info or {}).get("assets", []) or []
              if (a.get("name", "") or "").lower().endswith(".exe")
              and a.get("url")]
    if not assets:
        return None
    want = {n.lower() for n in (exe_names or ())}
    for a in assets:
        if a["name"].lower() in want:
            return a
    return assets[0]


def pick_setup_asset(info):
    """Setup installer asset: PKGViewer-Setup-*.exe first, else first Setup*.exe."""
    assets = (info or {}).get("assets", []) or []
    for a in assets:
        n = (a.get("name", "") or "").lower()
        if n.startswith("pkgviewer-setup") and n.endswith(".exe") and a.get("url"):
            return a
    for a in assets:
        n = (a.get("name", "") or "").lower()
        if "setup" in n and n.endswith(".exe") and a.get("url"):
            return a
    return None


def install_dir():
    """Install dir when running as installed exe, else None."""
    try:
        if not getattr(_sys, "frozen", False):
            return None
        d = _os.path.dirname(_os.path.abspath(_sys.executable))
        if _os.path.isfile(_os.path.join(d, "unins000.exe")):
            return d
    except Exception:
        pass
    return None


def is_installed():
    """True when running from an Inno-installed location."""
    return install_dir() is not None


def run_setup_and_exit(setup_path):
    """Launch Setup installer (silent, per-user) and return True.

    Caller must exit immediately so Setup can overwrite the running exe.
    """
    try:
        flags = getattr(_subprocess, "DETACHED_PROCESS", 0)
        _subprocess.Popen(
            [setup_path, "/SP-", "/SILENT", "/NORESTART",
             "/CLOSEAPPLICATIONS"],
            stdin=_subprocess.DEVNULL, stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL, creationflags=flags,
            close_fds=False)
        return True
    except Exception:
        return False


def download(url, dest, progress=None, timeout=120):
    """Download url to dest. progress(got_bytes, total_bytes) is optional."""
    req = _ureq.Request(url, headers={"User-Agent": "updater"})
    with _ureq.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        try:
            total = int(r.getheader("Content-Length") or 0)
        except Exception:
            total = 0
        got = 0
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress:
                try:
                    progress(got, total)
                except Exception:
                    pass


def stage_and_restart(new_path):
    """Swap the running exe with new_path and relaunch it.

    Returns True if the swap was launched (caller must exit immediately).
    Returns False when not running as a frozen exe (dev mode) — the caller
    should then tell the user where the file was saved.
    """
    if not getattr(_sys, "frozen", False):
        return False
    exe = _os.path.abspath(_sys.executable)
    bat = _os.path.join(_os.path.dirname(exe), "_update_swap.bat")
    with open(bat, "w", encoding="ascii", errors="replace") as f:
        f.write('@echo off\r\n'
                'timeout /t 3 /nobreak >nul\r\n'
                'copy /y "%s" "%s" >nul\r\n'
                'start "" "%s"\r\n'
                'del "%s" >nul 2>&1\r\n'
                'del "%%~f0" >nul 2>&1\r\n'
                % (new_path, exe, exe, new_path))
    flags = getattr(_subprocess, "DETACHED_PROCESS", 0)
    _subprocess.Popen(["cmd", "/c", bat], stdin=_subprocess.DEVNULL,
                      stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL,
                      creationflags=flags, close_fds=False)
    return True

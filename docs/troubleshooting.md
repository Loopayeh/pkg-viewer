# Windows: "Smart App Control blocked an app" / "Windows protected your PC"

PKG Viewer builds are **not code-signed**, so Windows treats them as coming from an unknown publisher. There are two different warnings, and only one of them can be clicked through.

| Warning | Who sees it | Can you get past it? |
|---|---|---|
| **Windows protected your PC** (SmartScreen, "Unknown publisher") | Almost everyone on Windows 10 / 11 | Yes — click **More info → Run anyway** |
| **Smart App Control blocked an app that may be unsafe** | Windows 11 with Smart App Control set to **On** (typical for clean installs and new PCs) | No button exists. See below |

Neither warning means the file is infected. It means Microsoft cannot verify *who published it*, because no one signed it.

---

## "Windows protected your PC" (SmartScreen)

1. Click **More info** on the dialog.
2. Click **Run anyway**.

The installer and the app are the same file you downloaded from Releases; the hash is listed on the release page if you want to check it.

---

## "Smart App Control blocked an app"

Smart App Control (SAC) is a Windows 11 feature that only runs apps it can verify. It has **no "Allow anyway" button**, **no per-app exception list**, and unblocking the file (`Unblock-File`, right-click → Unblock) or adding a Defender exclusion does **not** help. Renaming or moving the exe does not help either.

You have three options.

### Option 1 — Run from source (fastest, keeps SAC on)

SAC allows executables signed by a trusted publisher, and Python's `python.exe` / `pythonw.exe` are signed by the Python Software Foundation. So the app runs fine as a script:

1. Install Python 3.10+ from [python.org](https://www.python.org/downloads/) (tick **Add python.exe to PATH**).
2. Install the dependencies:
   ```
   pip install pillow tkinterdnd2 mkpfs cryptography
   ```
3. Download the source (Code → Download ZIP, or `git clone`), and run:
   ```
   PKGViewer.bat
   ```

Every feature works except single-file packaging. `pytsk3` (`.ffpkg` images) is optional and builds from source on Windows.

### Option 2 — Turn Smart App Control off

Windows Security → **App & browser control** → **Smart App Control settings** → **Off**.

Note: on Windows 11, once SAC is turned off it can only be turned back on by resetting or reinstalling Windows. The setting is also greyed out on work/school-managed PCs, where only an administrator can change it.

### Option 3 — Wait for a signed build

Signing the builds (see below) is the only fix that keeps SAC on and does not require Python. Until then, Options 1 and 2 are the workarounds.

---

## What does not work

- Right-click → Unblock, or `Unblock-File` in PowerShell
- Adding an exclusion in Windows Defender
- Renaming `PKGViewer.exe`, moving it to another folder, or re-zipping it
- Running as administrator
- Rebuilding the exe with PyInstaller (same unsigned result)

SAC checks the publisher signature chain, not the file name, path, or hash reputation alone.

Reinstalling the same version does not reliably help: the decision is made on the binary itself, so a fresh install of an identical, unsigned exe is blocked again. If a reinstall happens to work for you, the build or your PC's SAC state was different — do not count on it as a fix, and do not report it as one.

---

## For maintainers: signing

`Build-Release.bat` will sign the built exe automatically when a certificate is supplied:

- **`.pfx` file** — set `SIGN_PFX` and `SIGN_PFX_PASS`
- **Azure Trusted Signing** — set `SIGN_DLIB` (the `Azure.CodeSigning.Dlib.dll` path) and `SIGN_METADATA` (the metadata JSON path)

Without either variable the build is unsigned and unchanged.

Two things must be signed, not one:

1. `dist\PKGViewer.exe` — what SAC actually launches.
2. `PKGViewer-Setup-X.Y.Z.exe` — otherwise the installer is blocked before it ever copies the signed exe, and the in-app updater (`updater.py` downloads the Setup asset) fails silently on affected machines. `installer.iss` has the Inno Setup `SignTool` directives ready, commented out.

A certificate that chains to a trusted root is what satisfies SAC. Self-signed certificates installed into Trusted Root / Trusted Publishers are not reliable for this. New publishers may still need some reputation before SmartScreen stops warning, but the SAC block is resolved by a valid signature.

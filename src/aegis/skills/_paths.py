"""Turn the paths people (and small LLMs) say into real Windows paths.

"downloads", "my documents", "~/Desktop", "%USERPROFILE%\\Music" and hallucinated
placeholders such as "C:\\Users\\[username]\\Downloads" all resolve to the real folder.
"""

from __future__ import annotations

import functools
import os
import re
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path

# Windows Known Folder IDs (the real location, even when redirected to OneDrive).
_KNOWN_FOLDER_IDS = {
    "desktop": "B4BFCC3A-DB2C-424C-B029-7FE99A87C641",
    "documents": "FDD39AD0-238F-46AF-ADB4-6C85480369C7",
    "downloads": "374DE290-123F-4565-9164-39C4925E467B",
    "pictures": "33E28130-4E1E-4676-835A-98395C3BC3BB",
    "music": "4BD8D571-6D19-48D3-BE97-422220080E43",
    "videos": "18989B1D-99B5-455B-841C-AB7C74E4DDFC",
}

# Other ways people name those folders.
_SYNONYMS = {
    "download": "downloads",
    "document": "documents",
    "docs": "documents",
    "photos": "pictures",
    "images": "pictures",
    "picture": "pictures",
    "video": "videos",
    "movies": "videos",
    "home": "home",
    "user": "home",
    "user folder": "home",
    "profile": "home",
}

_NAME_NOISE = re.compile(r"^(?:the |my )|(?: folder| directory| dir)$")
_USERS_PATH = re.compile(r"^([A-Za-z]:)[\\/]+users[\\/]+([^\\/]+)(?:[\\/]+(.*))?$", re.IGNORECASE)


def _windows_known_folder(folder_id: str) -> Path | None:
    import ctypes
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", wintypes.DWORD),
            ("Data2", wintypes.WORD),
            ("Data3", wintypes.WORD),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    u = uuid.UUID(folder_id)
    guid = GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))
    out = ctypes.c_wchar_p()
    shell32 = ctypes.windll.shell32
    if shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) != 0:
        return None
    try:
        return Path(out.value) if out.value else None
    finally:
        ctypes.windll.ole32.CoTaskMemFree(out)


@functools.cache
def known_folders() -> dict[str, Path]:
    """{'home': ..., 'desktop': ..., 'documents': ..., 'downloads': ..., ...} for this user."""
    home = Path.home()
    folders = {"home": home}
    for name, folder_id in _KNOWN_FOLDER_IDS.items():
        path = None
        if sys.platform == "win32":
            try:
                path = _windows_known_folder(folder_id)
            except Exception:  # pragma: no cover - API failure, fall back below
                path = None
        folders[name] = path or home / name.capitalize()
    return folders


def _folder_key(text: str) -> str | None:
    key = text.strip().strip("\"'").rstrip("\\/").lower()
    for _ in range(2):
        key = _NAME_NOISE.sub("", key).strip()
    key = _SYNONYMS.get(key, key)
    return key if key in _KNOWN_FOLDER_IDS or key == "home" else None


def resolve_user_path(raw: str, folders: Mapping[str, Path]) -> Path:
    """Best-effort mapping of a spoken/LLM path to a real path. Does not check existence."""
    text = raw.strip().strip("\"'")
    if key := _folder_key(text):
        return folders[key]

    text = os.path.expanduser(os.path.expandvars(text))
    home = folders["home"]

    # C:\Users\<placeholder or wrong name>\rest  ->  real home (+ known folder) + rest
    if m := _USERS_PATH.match(text):
        drive, user, rest = m.groups()
        if not Path(f"{drive}\\Users\\{user}").is_dir():
            return _join_under(home, rest or "", folders)

    path = Path(text)
    if not path.is_absolute():
        return _join_under(home, text, folders)
    return path


def _join_under(home: Path, rest: str, folders: Mapping[str, Path]) -> Path:
    parts = [p for p in re.split(r"[\\/]+", rest) if p]
    if not parts:
        return home
    if key := _folder_key(parts[0]):
        return folders[key].joinpath(*parts[1:])
    return home.joinpath(*parts)


def describe_folders(folders: Mapping[str, Path]) -> str:
    return ", ".join(f"{name.capitalize()} = {path}" for name, path in folders.items())

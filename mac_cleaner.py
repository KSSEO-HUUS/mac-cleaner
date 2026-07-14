#!/usr/bin/env python3
"""
mac_cleaner.py - macOS 가비지 파일 자동 정리 도구
사용법: python3 mac_cleaner.py
"""

import os
import argparse
import plistlib
import shlex
import shutil
import subprocess
import threading
import io
import re
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path

# ── 색상 ───────────────────────────────────────────────────
class C:
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    DIM    = "\033[2m"
    BOLD   = "\033[1m"
    RESET  = "\033[0m"

def bold(s):   return f"{C.BOLD}{s}{C.RESET}"
def green(s):  return f"{C.GREEN}{s}{C.RESET}"
def yellow(s): return f"{C.YELLOW}{s}{C.RESET}"
def red(s):    return f"{C.RED}{s}{C.RESET}"
def blue(s):   return f"{C.BLUE}{s}{C.RESET}"
def dim(s):    return f"{C.DIM}{s}{C.RESET}"


ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
DEBUG_LOG = Path("/tmp/앱클리너.log")


def debug_log(message: str):
    try:
        with DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(f"{message}\n")
    except Exception:
        pass


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)

# ── 용량 포맷 ──────────────────────────────────────────────
def fmt_size(b: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(b) < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

# ── 용량 계산 ──────────────────────────────────────────────
def get_effective_size(path: Path) -> int:
    """
    삭제 가능한 항목만 기준으로 용량을 계산한다.
    보호 파일은 제외해서, 정리 후 남는 껍데기 디렉터리가 재등장하지 않게 한다.
    """
    total = 0
    try:
        if path.is_file():
            return 0 if is_protected_path(path) else path.stat().st_size
        for entry in path.rglob("*"):
            try:
                if is_protected_path(entry):
                    continue
                if entry.is_file():
                    total += entry.stat().st_size
            except (PermissionError, OSError):
                pass
    except (PermissionError, OSError):
        pass
    return total


def get_size(path: Path) -> int:
    """호환성을 위해 남겨둔 별칭."""
    return get_effective_size(path)

# ── 삭제 ───────────────────────────────────────────────────
PROTECTED_FILENAMES = {
    ".com.apple.containermanagerd.metadata.plist",
    "CodeResources",
}

PROTECTED_PREFIXES = (
    ".com.apple.containermanagerd",
)

COMMON_EXCLUDE_NAMES = {
    ".ds_store",
    "app store",
    "audio",
    "byhost",
    "crashreporter",
    "default.store",
    "default.store-shm",
    "default.store-wal",
    "dock",
    "gamekit",
    "geoservices",
    "icloud",
    "knowledge-agent.plist",
    "locationaccessstored",
    "mobilemeaccounts.plist",
    "passkit",
    "photossearch.aapbz",
    "photosupgrade.aapbz",
    "opendirectory",
    "segment",
    "systemconfiguration",
    "script editor",
    "btserver",
    "adobe",
    "skylum software",
    "macphun software",
    "ilifemediabrowser",
    "logitech",
    "logitech.localized",
    "net.battle.plist",
}

def is_within_library(path: Path) -> bool:
    try:
        return Path("/Library") in path.parents or str(path).startswith("/Library/")
    except Exception:
        return False


def should_skip_candidate(path: Path) -> bool:
    """
    공통적으로 지우지 않는 항목을 걸러낸다.
    - macOS 보호 메타/서명 파일
    - 시스템/예약 이름
    - /Library 아래에서 현재 사용자 권한으로 수정 불가한 항목
    """
    name = path.name.lower()
    if is_protected_path(path):
        return True
    if name in COMMON_EXCLUDE_NAMES:
        return True
    if is_within_library(path) and not os.access(path, os.W_OK):
        return True
    return False

def is_protected_path(path: Path) -> bool:
    """
    macOS가 관리하는 메타/서명 파일은 삭제 대상에서 제외한다.
    """
    name = path.name
    if name in PROTECTED_FILENAMES:
        return True
    if any(name.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return True
    return False


def remove_path_safe(path: Path) -> int:
    """
    보호 파일은 건너뛰고, 지울 수 있는 항목만 최대한 제거한다.
    반환값은 실제로 삭제된 용량이다.
    """
    if not path.exists() and not path.is_symlink():
        return 0

    if is_protected_path(path):
        print(yellow(f"    ↷ 보호 파일 건너뜀: {path.name}"))
        return 0

    if path.is_file() or path.is_symlink():
        try:
            size = 0 if is_protected_path(path) else path.stat().st_size
        except (PermissionError, OSError):
            size = 0
        try:
            path.unlink()
            return size
        except (PermissionError, OSError) as e:
            if not should_skip_candidate(path):
                print(red(f"    ✗ 삭제 실패: {path.name} ({e})"))
            return 0

    if path.is_dir():
        freed = 0
        try:
            children = list(path.iterdir())
        except (PermissionError, OSError) as e:
            if not should_skip_candidate(path):
                print(red(f"    ✗ 폴더 읽기 실패: {path.name} ({e})"))
            return 0

        for child in children:
            if is_protected_path(child):
                print(yellow(f"    ↷ 보호 파일 건너뜀: {child.name}"))
                continue
            freed += remove_path_safe(child)

        try:
            path.rmdir()
        except OSError:
            # 보호 파일이 남아 있거나 폴더가 비어 있지 않으면 그대로 둔다.
            pass
        return freed

    return 0


def delete_path(path: Path) -> int:
    return remove_path_safe(path)

HOME = Path.home()

# ══════════════════════════════════════════════════════════
# 1. 설치된 앱 목록 수집
# ══════════════════════════════════════════════════════════

def get_installed_apps() -> dict:
    """
    /Applications 와 ~/Applications 스캔.
    반환: { bundle_id: app_name, ... }  + name→bundle_id 역방향
    """
    apps = {}          # bundle_id  → display_name
    name_to_id = {}    # lower_name → bundle_id

    search_dirs = [
        Path("/Applications"),
        HOME / "Applications",
        Path("/Applications/Setapp"),  # Setapp 사용자
    ]

    for app_dir in search_dirs:
        if not app_dir.exists():
            continue
        for app in app_dir.rglob("*.app"):
            plist_path = app / "Contents" / "Info.plist"
            if not plist_path.exists():
                continue
            try:
                with open(plist_path, "rb") as f:
                    info = plistlib.load(f)
                bundle_id = info.get("CFBundleIdentifier", "").lower()
                display   = info.get("CFBundleName") or info.get("CFBundleDisplayName") or app.stem
                if bundle_id:
                    apps[bundle_id] = display
                    name_to_id[display.lower()] = bundle_id
                    name_to_id[app.stem.lower()] = bundle_id
            except Exception:
                pass

    return apps, name_to_id


# ══════════════════════════════════════════════════════════
# 2. 잔여파일 탐색 (핵심 로직)
# ══════════════════════════════════════════════════════════

# 잔여파일이 숨어있는 경로들
ORPHAN_SEARCH_DIRS = [
    HOME / "Library" / "Caches",
    HOME / "Library" / "Logs",
    HOME / "Library" / "LaunchAgents",
]

OS_UPDATE_TARGETS = [
    {
        "name": "/Library/Updates",
        "desc": "macOS 업데이트 임시 파일/패키지",
        "paths": [Path("/Library/Updates")],
        "mode": "children",
    },
    {
        "name": "/macOS Install Data",
        "desc": "macOS 설치 후 남는 잔여 데이터",
        "paths": [Path("/macOS Install Data")],
        "mode": "children",
    },
]

# 절대 건드리면 안 되는 bundle_id 패턴 (Apple 시스템)
SYSTEM_PREFIXES = (
    "com.apple.",
    "com.microsoft.",   # Office 365 사용자 보호
    "io.cursor.",
    "com.google.keystone",  # Google 업데이터
)

# 폴더명에서 bundle_id 또는 앱 이름 추출 시도
def extract_candidate(name: str) -> list[str]:
    """
    'com.tinyspeck.slackmacgap.plist' → ['com.tinyspeck.slackmacgap']
    'Slack'                            → ['slack']
    'group.com.apple.notes'            → ['com.apple.notes']
    """
    name = name.removesuffix(".plist").removesuffix(".app")
    candidates = [name.lower()]

    # group. 접두어 제거
    if name.lower().startswith("group."):
        candidates.append(name[6:].lower())

    # reversed bundle id → 앱 이름 추출 시도 (마지막 컴포넌트)
    parts = name.split(".")
    if len(parts) >= 3:
        candidates.append(parts[-1].lower())          # slackmacgap
        candidates.append(".".join(parts).lower())    # 전체 bundle id
        # 앞쪽 bundle-id 접두어도 함께 후보로 넣어 App / Helper / Extension 계열을 공통 처리
        for i in range(len(parts) - 1, 1, -1):
            candidates.append(".".join(parts[:i]).lower())

    # 중복 제거 후 반환
    return list(dict.fromkeys(candidates))


def find_orphans(installed_apps: dict, name_to_id: dict) -> list[dict]:
    """
    설치된 앱과 매칭되지 않는 잔여파일 탐색.
    반환: [{ path, guessed_app, size }, ...]
    """
    orphans = []
    seen = set()

    for search_dir in ORPHAN_SEARCH_DIRS:
        if not search_dir.exists():
            continue

        try:
            entries = list(search_dir.iterdir())
        except PermissionError:
            continue

        for entry in entries:
            if entry in seen:
                continue
            seen.add(entry)

            if should_skip_candidate(entry):
                continue

            candidates = extract_candidate(entry.name)

            # 시스템 항목 제외
            if any(c.startswith(SYSTEM_PREFIXES) for c in candidates):
                continue

            # 현재 설치된 앱과 매칭되는지 확인
            matched = False
            for c in candidates:
                if c in installed_apps:
                    matched = True
                    break
                if c in name_to_id:
                    matched = True
                    break
                # bundle_id 부분 매칭 (com.xxx.AppName)
                for bid in installed_apps:
                    if c in bid or bid in c:
                        matched = True
                        break
                if matched:
                    break

            if not matched:
                size = get_effective_size(entry)
                if size < 1024:  # 1KB 미만 무시
                    continue
                # 어떤 앱의 잔여인지 추측
                guessed = candidates[-1] if candidates else entry.name
                orphans.append({
                    "path": entry,
                    "guessed_app": guessed,
                    "size": size,
                })

    # 크기 내림차순 정렬
    orphans.sort(key=lambda x: x["size"], reverse=True)
    return orphans


def scan_os_update_leftovers() -> list[dict]:
    results = []
    for t in OS_UPDATE_TARGETS:
        existing = [p for p in t["paths"] if p.exists()]
        if not existing:
            continue
        size = sum(get_effective_size(p) for p in existing if not should_skip_candidate(p))
        if size < 1024:
            continue
        results.append({**t, "existing_paths": existing, "size": size})
    return results


# ══════════════════════════════════════════════════════════
# 3. OS 업데이트 잔여물
# ══════════════════════════════════════════════════════════

CACHE_TARGETS = [
    {
        "name": "사용자 캐시",
        "desc": "~/Library/Caches 하위",
        "paths": [HOME / "Library" / "Caches"],
        "mode": "children",
    },
    {
        "name": "시스템 로그",
        "desc": "~/Library/Logs 하위",
        "paths": [HOME / "Library" / "Logs"],
        "mode": "children",
    },
    {
        "name": "휴지통",
        "desc": "~/.Trash 내 파일",
        "paths": [HOME / ".Trash"],
        "mode": "children",
    },
    {
        "name": "Xcode DerivedData",
        "desc": "Xcode 빌드 캐시",
        "paths": [HOME / "Library" / "Developer" / "Xcode" / "DerivedData"],
        "mode": "children",
    },
    {
        "name": "iOS DeviceSupport",
        "desc": "구버전 iOS 기기 지원 파일",
        "paths": [
            HOME / "Library" / "Developer" / "Xcode" / "iOS DeviceSupport",
            HOME / "Library" / "Developer" / "Xcode" / "watchOS DeviceSupport",
        ],
        "mode": "children",
    },
    {
        "name": "npm 캐시",
        "desc": "~/.npm/_cacache",
        "paths": [HOME / ".npm" / "_cacache"],
        "mode": "self",
    },
    {
        "name": "pip 캐시",
        "desc": "Python 패키지 캐시",
        "paths": [HOME / "Library" / "Caches" / "pip"],
        "mode": "self",
    },
    {
        "name": "Gradle 캐시",
        "desc": "Android/Java 빌드 캐시",
        "paths": [HOME / ".gradle" / "caches"],
        "mode": "self",
    },
    {
        "name": "Homebrew 캐시",
        "desc": "brew 다운로드/빌드 캐시",
        "paths": [HOME / "Library" / "Caches" / "Homebrew"],
        "mode": "self",
    },
    {
        "name": "Yarn 캐시",
        "desc": "yarn 패키지 캐시",
        "paths": [HOME / "Library" / "Caches" / "Yarn"],
        "mode": "self",
    },
    {
        "name": "pnpm 캐시",
        "desc": "pnpm 패키지 저장소",
        "paths": [HOME / "Library" / "pnpm" / "store", HOME / ".local" / "share" / "pnpm" / "store"],
        "mode": "self",
    },
    {
        "name": "CocoaPods 캐시",
        "desc": "CocoaPods 다운로드 캐시",
        "paths": [HOME / "Library" / "Caches" / "CocoaPods"],
        "mode": "self",
    },
    {
        "name": "Xcode Archives",
        "desc": "Xcode 아카이브 빌드",
        "paths": [HOME / "Library" / "Developer" / "Xcode" / "Archives"],
        "mode": "children",
    },
    {
        "name": "iOS/iPadOS 기기 백업",
        "desc": "MobileSync 백업 (필요한 백업이 없는지 확인)",
        "paths": [HOME / "Library" / "Application Support" / "MobileSync" / "Backup"],
        "mode": "children",
    },
    {
        "name": "Mail 다운로드",
        "desc": "메일 첨부파일 다운로드 캐시",
        "paths": [HOME / "Library" / "Containers" / "com.apple.mail" / "Data" / "Library" / "Mail Downloads"],
        "mode": "children",
    },
    {
        "name": "시스템 업데이트 캐시",
        "desc": "/Library/Caches/com.apple.SoftwareUpdate",
        "paths": [Path("/Library/Caches/com.apple.SoftwareUpdate")],
        "mode": "children",
    },
]

def scan_caches() -> list[dict]:
    results = []
    for t in CACHE_TARGETS:
        existing = [p for p in t["paths"] if p.exists()]
        if not existing:
            continue
        size = sum(get_effective_size(p) for p in existing if not should_skip_candidate(p))
        if size < 1024:
            continue
        results.append({**t, "existing_paths": existing, "size": size})
    return results


# ══════════════════════════════════════════════════════════
# 3-b. 관리자 권한이 필요한 시스템 항목 (sudo)
# ══════════════════════════════════════════════════════════
# 현재 사용자 권한으로는 지울 수 없어, 삭제 시 관리자 암호를 받아야 한다.

ADMIN_TARGETS = [
    {
        "name": "시스템 로그",
        "desc": "/private/var/log (관리자 권한 필요)",
        "paths": [Path("/private/var/log")],
        "mode": "children",
    },
    {
        "name": "SoftwareUpdate 자산",
        "desc": "MobileAsset 소프트웨어 업데이트 자산 (SIP로 막힐 수 있음)",
        "paths": [Path("/System/Library/AssetsV2/com_apple_MobileAsset_SoftwareUpdate")],
        "mode": "children",
    },
]


def scan_admin_targets() -> list[dict]:
    """관리자 권한이 필요한 시스템 항목을 스캔한다. 존재하면 표시(용량은 근사치)."""
    results = []
    for t in ADMIN_TARGETS:
        existing = [p for p in t["paths"] if p.exists()]
        if not existing:
            continue
        size = 0
        for p in existing:
            try:
                size += get_effective_size(p)
            except (PermissionError, OSError):
                pass
        results.append({**t, "existing_paths": existing, "size": size})
    return results


# ══════════════════════════════════════════════════════════
# 3-c. 외부 도구 명령으로 정리하는 항목
# ══════════════════════════════════════════════════════════
# 용량을 미리 계산하기 어렵거나, 전용 명령으로 비우는 게 안전한 항목들.
# check: 해당 실행파일이 있을 때만 노출(None 이면 항상).
# admin: 관리자 권한 필요. danger: 되돌릴 수 없는 위험 항목.

COMMAND_TARGETS = [
    {
        "name": "Homebrew cleanup",
        "desc": "brew cleanup -s + 다운로드 캐시 삭제",
        "check": "brew",
        "cmd": 'brew cleanup -s; rm -rf "$(brew --cache)"',
        "admin": False,
        "danger": False,
    },
    {
        "name": "사용하지 않는 시뮬레이터",
        "desc": "xcrun simctl delete unavailable",
        "check": "xcrun",
        "cmd": "xcrun simctl delete unavailable",
        "admin": False,
        "danger": False,
    },
    {
        "name": "Docker 정리 (볼륨 포함)",
        "desc": "docker system prune -af --volumes — 볼륨/이미지까지 삭제(위험)",
        "check": "docker",
        "cmd": "docker system prune -af --volumes",
        "admin": False,
        "danger": True,
    },
    {
        "name": "Time Machine 로컬 스냅샷",
        "desc": "tmutil thinlocalsnapshots (관리자 권한 필요)",
        "check": None,
        "cmd": "tmutil thinlocalsnapshots / 999999999999 4",
        "admin": True,
        "danger": False,
    },
]


def scan_command_targets() -> list[dict]:
    results = []
    for t in COMMAND_TARGETS:
        check = t.get("check")
        if check and not shutil.which(check):
            continue
        results.append(dict(t))
    return results


# ══════════════════════════════════════════════════════════
# 3-d. 스캔 결과를 선택 가능한 단일 목록(entry)으로 통합
# ══════════════════════════════════════════════════════════
# 각 entry: kind, category, label, desc, size(int|None), target, default, admin, danger

def gather_entries() -> list[dict]:
    installed_apps, name_to_id = get_installed_apps()
    orphans = find_orphans(installed_apps, name_to_id)
    os_updates = scan_os_update_leftovers()
    cache_results = scan_caches()
    admin_results = scan_admin_targets()
    command_results = scan_command_targets()

    entries = []
    for r in os_updates:
        entries.append({"kind": "path", "category": "🧩 OS 업데이트 잔여물",
                        "label": r["name"], "desc": r["desc"], "size": r["size"],
                        "target": r, "default": True, "admin": False, "danger": False})
    for r in cache_results:
        entries.append({"kind": "path", "category": "🗂 일반 캐시 / 로그",
                        "label": r["name"], "desc": r["desc"], "size": r["size"],
                        "target": r, "default": True, "admin": False, "danger": False})
    for o in orphans:
        entries.append({"kind": "orphan", "category": "👻 삭제된 앱 잔여파일",
                        "label": o["path"].name, "desc": str(o["path"].parent), "size": o["size"],
                        "target": o, "default": True, "admin": False, "danger": False})
    for r in command_results:
        admin = r.get("admin", False)
        danger = r.get("danger", False)
        entries.append({"kind": "command", "category": "🛠 도구 명령 정리",
                        "label": r["name"], "desc": r["desc"], "size": None,
                        "target": r, "default": (not admin and not danger),
                        "admin": admin, "danger": danger})
    for r in admin_results:
        entries.append({"kind": "admin_path", "category": "🔒 시스템 (관리자 권한)",
                        "label": r["name"], "desc": r["desc"], "size": r["size"],
                        "target": r, "default": False, "admin": True, "danger": False})
    return entries


# ══════════════════════════════════════════════════════════
# 3-e. entry 실행 (사용자 / 명령 / 관리자 배치)
# ══════════════════════════════════════════════════════════

def run_command_target(t: dict, emit=print):
    emit(f"  → {t['name']}")
    try:
        r = subprocess.run(t["cmd"], shell=True, capture_output=True, text=True, timeout=1200)
        if r.returncode == 0:
            emit(green(f"    ✓ {t['name']}"))
        else:
            emit(red(f"    ✗ {t['name']}: {(r.stderr or '').strip()[:200]}"))
    except Exception as e:
        emit(red(f"    ✗ {t['name']}: {e}"))


def run_admin_batch(admin_paths: list[dict], admin_cmds: list[dict], emit=print) -> bool:
    """관리자 권한 항목을 한 번의 암호 입력으로 일괄 실행한다."""
    parts = []
    for t in admin_paths:
        for p in t.get("existing_paths", t["paths"]):
            q = shlex.quote(str(p))
            if t.get("mode") == "self":
                parts.append(f"rm -rf {q} 2>/dev/null || true")
            else:  # children
                parts.append(f"rm -rf {q}/* 2>/dev/null || true")
    for t in admin_cmds:
        parts.append(f"{t['cmd']} 2>/dev/null || true")

    if not parts:
        return True

    body = " ; ".join(parts)
    apple = body.replace("\\", "\\\\").replace('"', '\\"')
    script = f'do shell script "{apple}" with administrator privileges'
    emit("  → 관리자 항목 정리 (암호 입력 필요)")
    try:
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=1800)
        if r.returncode == 0:
            emit(green("    ✓ 관리자 항목 정리 완료"))
            return True
        emit(red(f"    ✗ 관리자 항목 취소/실패: {(r.stderr or '').strip()[:200]}"))
        return False
    except Exception as e:
        emit(red(f"    ✗ 관리자 항목 실패: {e}"))
        return False


def execute_entries(selected: list[dict], emit=print) -> int:
    """선택된 entry들을 종류별로 나눠 실행한다. 반환: 사용자 경로에서 확보한 용량."""
    freed = 0
    # 1) 사용자 권한 경로/잔여파일 삭제
    for e in selected:
        if e["kind"] == "path":
            freed += clean_caches([e["target"]])
        elif e["kind"] == "orphan":
            freed += clean_orphans([e["target"]])
    # 2) 관리자 불필요 명령
    for e in selected:
        if e["kind"] == "command" and not e["target"].get("admin"):
            run_command_target(e["target"], emit)
    # 3) 관리자 배치 (경로 rm + 관리자 명령)를 한 번에
    admin_paths = [e["target"] for e in selected if e["kind"] == "admin_path"]
    admin_cmds = [e["target"] for e in selected if e["kind"] == "command" and e["target"].get("admin")]
    if admin_paths or admin_cmds:
        run_admin_batch(admin_paths, admin_cmds, emit)
    return freed


# ══════════════════════════════════════════════════════════
# 4. 출력 / UI
# ══════════════════════════════════════════════════════════

def divider(emit=print):
    emit(bold("─" * 58))

def section(title, emit=print):
    emit("")
    emit(bold("═" * 58))
    emit(bold(f"  {title}"))
    emit(bold("═" * 58))


def print_cache_preview(results: list[dict], emit=print):
    section("🗂  일반 캐시 / 로그", emit=emit)
    for i, r in enumerate(results, 1):
        bar = fmt_size(r["size"]).rjust(10)
        emit(f"  {blue(str(i).rjust(2))}. {r['name']:<26} {yellow(bar)}")
        emit(f"      {dim(r['desc'])}")
    emit("")
    total = sum(r["size"] for r in results)
    emit(f"  {'소계':.<26} {green(fmt_size(total).rjust(10))}")


def print_orphan_preview(orphans: list[dict], emit=print):
    section("👻  삭제된 앱 잔여파일", emit=emit)

    if not orphans:
        emit(green("  잔여파일 없음 ✓"))
        return

    offset = 200  # 번호 충돌 방지용 오프셋
    for i, o in enumerate(orphans, 1):
        bar = fmt_size(o["size"]).rjust(10)
        emit(f"  {blue(str(offset + i).rjust(3))}. {o['path'].name:<30} {yellow(bar)}")
        emit(f"       {dim(o['path'].parent)}")

    emit("")
    total = sum(o["size"] for o in orphans)
    emit(f"  {'소계':.<26} {green(fmt_size(total).rjust(10))}")


def print_os_update_preview(results: list[dict], emit=print):
    section("🧩  OS 업데이트 잔여물", emit=emit)

    if not results:
        emit(green("  정리 대상 없음 ✓"))
        return

    offset = 100  # 번호 충돌 방지용 오프셋
    for i, r in enumerate(results, 1):
        bar = fmt_size(r["size"]).rjust(10)
        emit(f"  {blue(str(offset + i).rjust(3))}. {r['name']:<30} {yellow(bar)}")
        emit(f"       {dim(r['desc'])}")

    emit("")
    total = sum(r["size"] for r in results)
    emit(f"  {'소계':.<26} {green(fmt_size(total).rjust(10))}")


def parse_selection(ans: str, cache_results, os_updates, orphans) -> tuple[list, list, list]:
    """입력 파싱 → (선택된 캐시 목록, 선택된 OS 업데이트 목록, 선택된 orphan 목록)"""
    if ans == "all":
        return cache_results, os_updates, orphans

    sel_cache = []
    sel_updates = []
    sel_orphan = []
    CACHE_OFFSET = 1
    UPDATE_OFFSET = 100
    ORPHAN_OFFSET = 200

    for token in ans.split():
        if not token.isdigit():
            continue
        n = int(token)
        if CACHE_OFFSET <= n < CACHE_OFFSET + len(cache_results):
            sel_cache.append(cache_results[n - 1])
        elif UPDATE_OFFSET < n <= UPDATE_OFFSET + len(os_updates):
            sel_updates.append(os_updates[n - UPDATE_OFFSET - 1])
        elif ORPHAN_OFFSET < n <= ORPHAN_OFFSET + len(orphans):
            sel_orphan.append(orphans[n - ORPHAN_OFFSET - 1])

    return sel_cache, sel_updates, sel_orphan


def gather_scan_results():
    installed_apps, name_to_id = get_installed_apps()
    orphans = find_orphans(installed_apps, name_to_id)
    os_updates = scan_os_update_leftovers()
    cache_results = scan_caches()
    return installed_apps, name_to_id, orphans, os_updates, cache_results


class CleanerGUI:
    def __init__(self):
        try:
            from AppKit import (
                NSApplication,
                NSApplicationActivationPolicyRegular,
                NSBackingStoreBuffered,
                NSButton,
                NSFont,
                NSMakeRect,
                NSScrollView,
                NSRunningApplication,
                NSView,
                NSWindow,
                NSApplicationActivateAllWindows,
                NSApplicationActivateIgnoringOtherApps,
                NSWindowStyleMaskClosable,
                NSWindowStyleMaskMiniaturizable,
                NSWindowStyleMaskResizable,
                NSWindowStyleMaskTitled,
                NSTextField,
                NSTextView,
                NSAlert,
            )
        except Exception as e:
            raise RuntimeError(f"AppKit를 사용할 수 없습니다: {e}") from e

        self.NSApplication = NSApplication
        self.NSApplicationActivationPolicyRegular = NSApplicationActivationPolicyRegular
        self.NSApplicationActivateAllWindows = NSApplicationActivateAllWindows
        self.NSApplicationActivateIgnoringOtherApps = NSApplicationActivateIgnoringOtherApps
        self.NSBackingStoreBuffered = NSBackingStoreBuffered
        self.NSButton = NSButton
        self.NSFont = NSFont
        self.NSMakeRect = NSMakeRect
        self.NSScrollView = NSScrollView
        self.NSRunningApplication = NSRunningApplication
        self.NSView = NSView
        self.NSWindow = NSWindow
        self.NSWindowStyleMaskClosable = NSWindowStyleMaskClosable
        self.NSWindowStyleMaskMiniaturizable = NSWindowStyleMaskMiniaturizable
        self.NSWindowStyleMaskResizable = NSWindowStyleMaskResizable
        self.NSWindowStyleMaskTitled = NSWindowStyleMaskTitled
        self.NSTextField = NSTextField
        self.NSTextView = NSTextView
        self.NSAlert = NSAlert

        self.app = self.NSApplication.sharedApplication()
        self.app.setActivationPolicy_(self.NSApplicationActivationPolicyRegular)

        style = (
            self.NSWindowStyleMaskTitled
            | self.NSWindowStyleMaskClosable
            | self.NSWindowStyleMaskResizable
            | self.NSWindowStyleMaskMiniaturizable
        )
        self.window = self.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            self.NSMakeRect(0, 0, 860, 640),
            style,
            self.NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("앱클리너")
        self.window.center()
        self.window.setReleasedWhenClosed_(False)

        content = self.window.contentView()
        content.setWantsLayer_(True)

        title = self.NSTextField.labelWithString_("앱클리너")
        title.setFrame_(self.NSMakeRect(20, 590, 260, 32))
        title.setFont_(self.NSFont.boldSystemFontOfSize_(26))
        title.setTextColor_(self._color(0.08, 0.27, 0.23))
        content.addSubview_(title)

        subtitle = self.NSTextField.labelWithString_(
            "실행 버튼을 누르면 스캔 결과를 보여주고, 계속 진행할지 묻습니다."
        )
        subtitle.setFrame_(self.NSMakeRect(20, 562, 760, 22))
        subtitle.setFont_(self.NSFont.systemFontOfSize_(12))
        subtitle.setTextColor_(self._color(0.3, 0.42, 0.39))
        content.addSubview_(subtitle)

        def _mk_button(title, x, w, action):
            b = self.NSButton.alloc().initWithFrame_(self.NSMakeRect(x, 524, w, 32))
            b.setTitle_(title)
            b.setBezelStyle_(1)
            b.setTarget_(self)
            b.setAction_(action)
            content.addSubview_(b)
            return b

        self.button = _mk_button("스캔", 20, 90, "startScan:")
        self.selectAllButton = _mk_button("전체 선택", 116, 96, "selectAll:")
        self.deselectAllButton = _mk_button("전체 해제", 218, 96, "deselectAll:")
        self.deleteButton = _mk_button("선택 삭제", 320, 110, "deleteSelected:")
        self.deleteButton.setEnabled_(False)
        self.selectAllButton.setEnabled_(False)
        self.deselectAllButton.setEnabled_(False)

        self.status = self.NSTextField.labelWithString_("대기 중")
        self.status.setFrame_(self.NSMakeRect(440, 530, 400, 20))
        self.status.setFont_(self.NSFont.systemFontOfSize_(12))
        self.status.setTextColor_(self._color(0.3, 0.42, 0.39))
        content.addSubview_(self.status)

        # ── 체크박스 선택 목록 (스캔 결과) ──
        pick_label = self.NSTextField.labelWithString_("정리할 항목을 골라 체크하세요:")
        pick_label.setFrame_(self.NSMakeRect(20, 500, 500, 18))
        pick_label.setFont_(self.NSFont.systemFontOfSize_(11))
        pick_label.setTextColor_(self._color(0.48, 0.56, 0.53))
        content.addSubview_(pick_label)

        self.scrollCheck = self.NSScrollView.alloc().initWithFrame_(self.NSMakeRect(20, 250, 820, 248))
        self.scrollCheck.setHasVerticalScroller_(True)
        self.scrollCheck.setBorderType_(1)

        NSView = self.NSView

        class _FlippedView(NSView):
            def isFlipped(self):
                return True

        self.checkContainer = _FlippedView.alloc().initWithFrame_(self.NSMakeRect(0, 0, 800, 248))
        self.scrollCheck.setDocumentView_(self.checkContainer)
        content.addSubview_(self.scrollCheck)
        self.checkboxes = []  # [(NSButton, entry), ...]

        # ── 로그 출력 ──
        self.scroll = self.NSScrollView.alloc().initWithFrame_(self.NSMakeRect(20, 20, 820, 218))
        self.scroll.setHasVerticalScroller_(True)
        self.scroll.setBorderType_(1)

        self.textView = self.NSTextView.alloc().initWithFrame_(self.NSMakeRect(0, 0, 820, 218))
        self.textView.setEditable_(False)
        self.textView.setSelectable_(True)
        self.textView.setRichText_(False)
        self.textView.setAutomaticQuoteSubstitutionEnabled_(False)
        self.textView.setFont_(self.NSFont.fontWithName_size_("Menlo", 12) or self.NSFont.systemFontOfSize_(12))
        self.textView.setString_("‘스캔’을 누르면 정리 후보가 위 목록에 나타납니다.\n🔒 = 관리자 암호 필요, ⚠️ = 되돌릴 수 없는 위험 항목(기본 해제).")
        self.scroll.setDocumentView_(self.textView)
        content.addSubview_(self.scroll)

        self.delegate = None

    def _append(self, text: str):
        text = strip_ansi(text)
        current = self.textView.string() or ""
        if current:
            current += "\n"
        self.textView.setString_(current + text)

    def _set_status(self, text: str):
        self.status.setStringValue_(text)

    def _color(self, r, g, b):
        from AppKit import NSColor
        return NSColor.colorWithCalibratedRed_green_blue_alpha_(r, g, b, 1.0)

    def _confirm(self, message: str) -> bool:
        alert = self.NSAlert.alloc().init()
        alert.setMessageText_("확인")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("계속")
        alert.addButtonWithTitle_("취소")
        return alert.runModal() == 1000

    def _alert(self, message: str):
        alert = self.NSAlert.alloc().init()
        alert.setMessageText_("앱클리너")
        alert.setInformativeText_(message)
        alert.addButtonWithTitle_("확인")
        alert.runModal()

    def _render_checkboxes(self, entries):
        # 이전 항목 제거
        for sub in list(self.checkContainer.subviews()):
            sub.removeFromSuperview()
        self.checkboxes = []

        row_h = 26
        width = 760
        y = 6
        last_cat = None
        for e in entries:
            if e["category"] != last_cat:
                last_cat = e["category"]
                hdr = self.NSTextField.labelWithString_(last_cat)
                hdr.setFrame_(self.NSMakeRect(8, y, width, 20))
                hdr.setFont_(self.NSFont.boldSystemFontOfSize_(13))
                hdr.setTextColor_(self._color(0.08, 0.27, 0.23))
                self.checkContainer.addSubview_(hdr)
                y += row_h

            if e["size"] is None:
                size_txt = "명령"
            else:
                size_txt = fmt_size(e["size"])
            mark = "  ⚠️" if e["danger"] else ("  🔒" if e.get("admin") else "")
            cb = self.NSButton.alloc().initWithFrame_(self.NSMakeRect(24, y, width, 22))
            cb.setButtonType_(3)  # NSSwitchButton (체크박스)
            cb.setTitle_(f"{e['label']}  —  {size_txt}{mark}")
            cb.setState_(1 if e["default"] else 0)
            self.checkContainer.addSubview_(cb)
            self.checkboxes.append((cb, e))
            y += row_h

        total_h = y + 8
        visible_h = self.scrollCheck.contentSize().height
        self.checkContainer.setFrame_(self.NSMakeRect(0, 0, 800, max(total_h, visible_h)))

    def selectAll_(self, sender):
        for cb, _e in self.checkboxes:
            cb.setState_(1)

    def deselectAll_(self, sender):
        for cb, _e in self.checkboxes:
            cb.setState_(0)

    def startScan_(self, sender):
        self.button.setEnabled_(False)
        self.deleteButton.setEnabled_(False)
        self.selectAllButton.setEnabled_(False)
        self.deselectAllButton.setEnabled_(False)
        self.textView.setString_("")
        self._set_status("스캔 중...")
        self._append("스캔을 시작합니다.")

        entries = gather_entries()
        self._entries = entries
        self._render_checkboxes(entries)

        total_all = sum(e["size"] for e in entries if e["size"])
        n_admin = sum(1 for e in entries if e.get("admin"))
        n_cmd = sum(1 for e in entries if e["kind"] == "command")
        self._append(f"후보 {len(entries)}개 · 즉시 확보 가능 약 {fmt_size(total_all)}"
                     + (f" · 명령 {n_cmd}개" if n_cmd else "")
                     + (f" · 관리자 {n_admin}개" if n_admin else ""))
        self._append("원하는 항목을 체크한 뒤 ‘선택 삭제’를 누르세요.")

        self.button.setEnabled_(True)
        if entries:
            self.deleteButton.setEnabled_(True)
            self.selectAllButton.setEnabled_(True)
            self.deselectAllButton.setEnabled_(True)
            self._set_status(f"{len(entries)}개 항목 · 선택 대기")
        else:
            self._set_status("정리할 항목 없음")
            self._append("정리할 항목이 없습니다.")

    def deleteSelected_(self, sender):
        selected = [e for (cb, e) in self.checkboxes if cb.state() == 1]
        if not selected:
            self._alert("선택된 항목이 없습니다.")
            return

        total = sum(e["size"] for e in selected if e["size"])
        has_admin = any(e.get("admin") for e in selected)
        has_danger = any(e["danger"] for e in selected)

        msg = f"{fmt_size(total)}(+명령 항목)를 삭제합니다. 계속할까요?"
        if has_admin:
            msg += "\n\n🔒 관리자 암호 입력창이 뜰 수 있습니다."
        if has_danger:
            msg += "\n\n⚠️ Docker 볼륨/이미지 등 되돌릴 수 없는 항목이 포함되어 있습니다."
        if not self._confirm(msg):
            self._append("사용자가 취소했습니다.")
            return

        self.button.setEnabled_(False)
        self.deleteButton.setEnabled_(False)
        self._set_status("정리 중...")
        self._append("")
        self._append("정리 중...")

        stdout_buf = io.StringIO()
        with redirect_stdout(stdout_buf):
            freed = execute_entries(selected)
        output = stdout_buf.getvalue()
        if output.strip():
            self._append(strip_ansi(output.rstrip()))

        self._append("")
        self._append(f"완료! 사용자 항목에서 {fmt_size(freed)} 확보했습니다.")
        self._set_status("완료 · 재스캔")
        self.button.setEnabled_(True)
        # 결과 반영을 위해 다시 스캔
        self.startScan_(None)
        self._alert(f"정리 완료.\n사용자 항목에서 {fmt_size(freed)}를 확보했습니다.")

    def run(self):
        from AppKit import NSObject

        class AppDelegate(NSObject):
            def initWithOwner_(self, owner):
                self = self.init()
                if self is None:
                    return None
                self.owner = owner
                return self

            def applicationDidFinishLaunching_(self, notification):
                debug_log("GUI delegate: applicationDidFinishLaunching")
                self.performSelector_withObject_afterDelay_("showWindow:", None, 0.0)

            def showWindow_(self, sender):
                debug_log("GUI delegate: showWindow")
                current_app = self.owner.NSRunningApplication.currentApplication()
                current_app.activateWithOptions_(
                    self.owner.NSApplicationActivateAllWindows
                    | self.owner.NSApplicationActivateIgnoringOtherApps
                )
                self.owner.window.makeKeyAndOrderFront_(None)
                self.owner.window.orderFrontRegardless()
                self.owner.app.activateIgnoringOtherApps_(True)
                self.owner.window.makeMainWindow()
                frame = self.owner.window.frame()
                debug_log(
                    "GUI delegate: window frame="
                    f"({frame.origin.x}, {frame.origin.y}, {frame.size.width}, {frame.size.height}), "
                    f"isVisible={self.owner.window.isVisible()}"
                )
                debug_log("GUI delegate: window ordered front")

            def applicationShouldTerminateAfterLastWindowClosed_(self, sender):
                return True

        self.delegate = AppDelegate.alloc().initWithOwner_(self)
        self.app.setDelegate_(self.delegate)
        self.app.finishLaunching()
        self.window.center()
        debug_log("GUI run: window centered")
        self.window.makeKeyAndOrderFront_(None)
        self.window.orderFrontRegardless()
        self.app.activateIgnoringOtherApps_(True)
        debug_log("GUI run: window ordered front before app.run()")
        self.app.run()


def parse_args():
    parser = argparse.ArgumentParser(
        description="macOS 가비지 파일 자동 정리 도구"
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="간단한 GUI 창으로 실행한다.",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="정리 항목 번호를 직접 선택한다.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="최종 확인 없이 바로 정리한다.",
    )
    return parser.parse_args()


# ══════════════════════════════════════════════════════════
# 5. 정리 실행
# ══════════════════════════════════════════════════════════

def clean_caches(selected: list[dict]) -> int:
    freed = 0
    for t in selected:
        print(f"  → {t['name']:<28}", end=" ", flush=True)
        f = 0
        for path in t["existing_paths"]:
            if not path.exists():
                continue
            if t["mode"] == "self":
                if should_skip_candidate(path):
                    print(yellow(f"    ↷ 보호/권한 항목 건너뜀: {path.name}"))
                    continue
                f += delete_path(path)
            else:  # children
                for child in list(path.iterdir()):
                    if should_skip_candidate(child):
                        print(yellow(f"    ↷ 보호/권한 항목 건너뜀: {child.name}"))
                        continue
                    f += delete_path(child)
        freed += f
        print(green(f"✓  {fmt_size(f)}"))
    return freed


def clean_orphans(selected: list[dict]) -> int:
    freed = 0
    for o in selected:
        print(f"  → {o['path'].name:<34}", end=" ", flush=True)
        if should_skip_candidate(o["path"]):
            print(yellow("↷ 보호/권한 대상 제외"))
            continue
        f = delete_path(o["path"])
        freed += f
        print(green(f"✓  {fmt_size(f)}"))
    return freed


def run_brew():
    if not shutil.which("brew"):
        return 0
    print(f"  → {'Homebrew cleanup':<28}", end=" ", flush=True)
    r = subprocess.run(["brew", "cleanup", "--prune=all"], capture_output=True, text=True)
    if r.returncode == 0:
        print(green("✓"))
    else:
        print(red("✗ 실패"))
    return 0


# ══════════════════════════════════════════════════════════
# 6. main
# ══════════════════════════════════════════════════════════

def main():
    args = parse_args()

    launched_from_gui = getattr(sys, "frozen", False) and not sys.stdout.isatty()

    if args.gui or launched_from_gui:
        try:
            debug_log("GUI start: entering CleanerGUI().run()")
            CleanerGUI().run()
        except Exception as e:
            debug_log("GUI error:\n" + traceback.format_exc())
            print(red(f"GUI 실행 실패: {e}"))
            print(yellow("터미널 모드로 계속합니다."))
        else:
            debug_log("GUI start: returned from run()")
            return

    print()
    print(bold(blue("  🧹 Mac Cleaner")))
    print()

    # ── 스캔 ──
    print("  스캔 중...", end="\r")
    entries = gather_entries()
    print("  스캔 완료.        ")

    if not entries:
        print(green("\n  ✓ Mac이 깨끗합니다!"))
        return

    # ── 미리보기 (번호 부여) ──
    last_cat = None
    for i, e in enumerate(entries, 1):
        if e["category"] != last_cat:
            last_cat = e["category"]
            section(last_cat)
        size_txt = "명령" if e["size"] is None else fmt_size(e["size"])
        mark = " ⚠️" if e["danger"] else (" 🔒" if e.get("admin") else "")
        print(f"  {blue(str(i).rjust(3))}. {e['label']:<30} {yellow(size_txt.rjust(10))}{mark}")
        print(f"       {dim(e['desc'])}")

    total_all = sum(e["size"] for e in entries if e["size"])
    print()
    divider()
    print(f"  {'즉시 확보 가능':.<26} {green(fmt_size(total_all).rjust(10))}")
    print(dim("  🔒 = 관리자 암호 필요, ⚠️ = 되돌릴 수 없는 위험 항목"))
    divider()

    # ── 선택 ──
    if args.interactive:
        print()
        print("  정리할 항목 번호 입력")
        print(dim("  (예: 1 3 5 / all / q)"))
        ans = input("  > ").strip().lower()
        if ans in ("q", "quit", ""):
            print(yellow("  취소했습니다."))
            return
        if ans == "all":
            selected = list(entries)
        else:
            idxs = {int(t) for t in ans.split() if t.isdigit()}
            selected = [e for i, e in enumerate(entries, 1) if i in idxs]
    else:
        # 기본: 안전 항목만(관리자/위험 제외). --yes 도 동일 기준.
        selected = [e for e in entries if e["default"]]

    if not selected:
        print(yellow("  선택된 항목이 없습니다."))
        return

    # ── 최종 확인 ──
    preview_total = sum(e["size"] for e in selected if e["size"])
    has_admin = any(e.get("admin") for e in selected)
    has_danger = any(e["danger"] for e in selected)
    if not args.yes:
        extra = ""
        if has_admin:
            extra += "  🔒 관리자 암호 입력이 필요할 수 있습니다.\n"
        if has_danger:
            extra += "  ⚠️ Docker 볼륨 등 되돌릴 수 없는 항목이 포함됩니다.\n"
        if extra:
            print("\n" + extra, end="")
        print(f"\n  {yellow(fmt_size(preview_total))}(+명령 항목) 삭제합니다. 계속할까요? [y/N] ", end="")
        if input().strip().lower() != "y":
            print(yellow("  취소했습니다."))
            return

    # ── 실행 ──
    section("🗑  정리 중")
    freed = execute_entries(selected)

    # ── 결과 ──
    print()
    print(bold("═" * 58))
    print(bold(green(f"  ✓ 완료!  사용자 항목에서 {fmt_size(freed)} 확보")))
    print(bold("═" * 58))
    print()


if __name__ == "__main__":
    main()

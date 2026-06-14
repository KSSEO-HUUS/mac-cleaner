#!/usr/bin/env python3
"""
mac_cleaner.py - macOS 가비지 파일 자동 정리 도구
사용법: python3 mac_cleaner.py
"""

import os
import argparse
import plistlib
import shutil
import subprocess
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
    HOME / "Library" / "Application Support",
    HOME / "Library" / "Preferences",
    HOME / "Library" / "Caches",
    HOME / "Library" / "Logs",
    HOME / "Library" / "Containers",
    HOME / "Library" / "Group Containers",
    HOME / "Library" / "LaunchAgents",
    Path("/Library/LaunchAgents"),
    Path("/Library/LaunchDaemons"),
    Path("/Library/Application Support"),
    Path("/Library/Preferences"),
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


# ══════════════════════════════════════════════════════════
# 3. 일반 캐시 정리 대상
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
# 4. 출력 / UI
# ══════════════════════════════════════════════════════════

def divider():
    print(bold("─" * 58))

def section(title):
    print()
    print(bold("═" * 58))
    print(bold(f"  {title}"))
    print(bold("═" * 58))


def print_cache_preview(results: list[dict]):
    section("🗂  일반 캐시 / 로그")
    for i, r in enumerate(results, 1):
        bar = fmt_size(r["size"]).rjust(10)
        print(f"  {blue(str(i).rjust(2))}. {r['name']:<26} {yellow(bar)}")
        print(f"      {dim(r['desc'])}")
    print()
    total = sum(r["size"] for r in results)
    print(f"  {'소계':.<26} {green(fmt_size(total).rjust(10))}")


def print_orphan_preview(orphans: list[dict]):
    section("👻  삭제된 앱 잔여파일")

    if not orphans:
        print(green("  잔여파일 없음 ✓"))
        return

    offset = 100  # 번호 충돌 방지용 오프셋
    for i, o in enumerate(orphans, 1):
        bar = fmt_size(o["size"]).rjust(10)
        print(f"  {blue(str(offset + i).rjust(3))}. {o['path'].name:<30} {yellow(bar)}")
        print(f"       {dim(o['path'].parent)}")

    print()
    total = sum(o["size"] for o in orphans)
    print(f"  {'소계':.<26} {green(fmt_size(total).rjust(10))}")


def parse_selection(ans: str, cache_results, orphans) -> tuple[list, list]:
    """입력 파싱 → (선택된 캐시 목록, 선택된 orphan 목록)"""
    if ans == "all":
        return cache_results, orphans

    sel_cache = []
    sel_orphan = []
    OFFSET = 100

    for token in ans.split():
        if not token.isdigit():
            continue
        n = int(token)
        if 1 <= n <= len(cache_results):
            sel_cache.append(cache_results[n - 1])
        elif OFFSET < n <= OFFSET + len(orphans):
            sel_orphan.append(orphans[n - OFFSET - 1])

    return sel_cache, sel_orphan


def parse_args():
    parser = argparse.ArgumentParser(
        description="macOS 가비지 파일 자동 정리 도구"
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

    print()
    print(bold(blue("  🧹 Mac Cleaner")))
    print()

    # ── 스캔 ──
    print("  [1/3] 설치된 앱 목록 수집 중...", end="\r")
    installed_apps, name_to_id = get_installed_apps()
    print(f"  [1/3] 설치된 앱 {len(installed_apps)}개 확인       ")

    print("  [2/3] 잔여파일 탐색 중...", end="\r")
    orphans = find_orphans(installed_apps, name_to_id)
    print(f"  [2/3] 잔여파일 {len(orphans)}개 발견       ")

    print("  [3/3] 캐시/로그 스캔 중...", end="\r")
    cache_results = scan_caches()
    print(f"  [3/3] 캐시 항목 {len(cache_results)}개 확인       ")

    # ── 미리보기 ──
    if cache_results:
        print_cache_preview(cache_results)
    if orphans:
        print_orphan_preview(orphans)

    total_all = (
        sum(r["size"] for r in cache_results)
        + sum(o["size"] for o in orphans)
    )
    print()
    divider()
    print(f"  {'총 확보 가능':.<26} {green(fmt_size(total_all).rjust(10))}")
    divider()

    if total_all == 0:
        print(green("\n  ✓ Mac이 깨끗합니다!"))
        return

    # ── 선택 ──
    if args.interactive:
        print()
        print("  정리할 항목 번호 입력")
        print(dim("  (예: 1 3 101 102 / all / q)"))
        ans = input("  > ").strip().lower()

        if ans in ("q", "quit", ""):
            print(yellow("  취소했습니다."))
            return

        sel_cache, sel_orphan = parse_selection(ans, cache_results, orphans)
    else:
        sel_cache, sel_orphan = cache_results, orphans

    if not sel_cache and not sel_orphan:
        print(yellow("  선택된 항목이 없습니다."))
        return

    # ── 최종 확인 ──
    preview_total = sum(r["size"] for r in sel_cache) + sum(o["size"] for o in sel_orphan)
    if not args.yes:
        print(f"\n  {yellow(fmt_size(preview_total))} 삭제합니다. 계속할까요? [y/N] ", end="")
        if input().strip().lower() != "y":
            print(yellow("  취소했습니다."))
            return

    # ── 실행 ──
    section("🗑  정리 중")
    freed = 0
    if sel_cache:
        freed += clean_caches(sel_cache)
    if sel_orphan:
        freed += clean_orphans(sel_orphan)

    # Homebrew
    if shutil.which("brew"):
        print(f"\n  Homebrew 캐시도 정리할까요? [y/N] ", end="")
        if input().strip().lower() == "y":
            run_brew()

    # ── 결과 ──
    print()
    print(bold("═" * 58))
    print(bold(green(f"  ✓ 완료!  총 {fmt_size(freed)} 확보")))
    print(bold("═" * 58))
    print()


if __name__ == "__main__":
    main()

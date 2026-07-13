#!/bin/bash
# macOS 업데이트/개발 캐시 통합 정리 스크립트
# 각 단계마다 확인을 받고 진행합니다 (전체를 한 번에 밀어버리지 않음).
#
# 사용법:
#   chmod +x deep_clean.sh
#   ./deep_clean.sh

set -u

confirm() {
    read -r -p "$1 [y/N] " reply
    [[ "$reply" =~ ^[Yy]$ ]]
}

section() {
    echo
    echo "==> $1"
}

echo "정리 전 디스크 사용량:"
df -h /

# 1. 시스템 업데이트 캐시
section "1. 시스템 업데이트 캐시 삭제"
ls -al /Library/Updates 2>/dev/null
if confirm "/Library/Updates 및 SoftwareUpdate 캐시를 삭제할까요?"; then
    sudo rm -rf /Library/Updates/*
    sudo rm -rf /Library/Caches/com.apple.SoftwareUpdate/*
    sudo rm -rf /System/Library/AssetsV2/com_apple_MobileAsset_SoftwareUpdate/* 2>/dev/null
fi

# 2. 사용자 캐시
section "2. 사용자 캐시 삭제 (~/Library/Caches)"
if confirm "사용자 캐시를 삭제할까요?"; then
    rm -rf ~/Library/Caches/*
fi

# 3. 시스템 로그
section "3. 시스템 로그 정리"
if confirm "/private/var/log 를 정리할까요?"; then
    sudo rm -rf /private/var/log/*
fi

# 4. Xcode 관련 (설치되어 있을 때만)
if [ -d ~/Library/Developer/Xcode ]; then
    section "4. Xcode 캐시/시뮬레이터 정리"
    if confirm "Xcode DerivedData / DeviceSupport / Archives 를 삭제할까요?"; then
        rm -rf ~/Library/Developer/Xcode/DerivedData/*
        rm -rf ~/Library/Developer/Xcode/iOS\ DeviceSupport/*
        rm -rf ~/Library/Developer/Xcode/Archives/*
    fi
    if command -v xcrun >/dev/null 2>&1; then
        if confirm "사용하지 않는 시뮬레이터를 삭제할까요?"; then
            xcrun simctl delete unavailable
        fi
    fi
fi

# 5. Homebrew 캐시
if command -v brew >/dev/null 2>&1; then
    section "5. Homebrew 캐시 정리"
    if confirm "brew cleanup 을 실행할까요?"; then
        brew cleanup -s
        rm -rf "$(brew --cache)"
    fi
fi

# 6. 패키지 매니저 캐시 (npm / yarn / pnpm / pip / CocoaPods)
section "6. 개발 패키지 매니저 캐시 정리"
if command -v npm >/dev/null 2>&1 && confirm "npm 캐시를 정리할까요?"; then
    npm cache clean --force
fi
if command -v yarn >/dev/null 2>&1 && confirm "yarn 캐시를 정리할까요?"; then
    yarn cache clean
fi
if command -v pnpm >/dev/null 2>&1 && confirm "pnpm 캐시를 정리할까요?"; then
    pnpm store prune
fi
if command -v pip >/dev/null 2>&1 && confirm "pip 캐시를 정리할까요?"; then
    pip cache purge
fi
if command -v pod >/dev/null 2>&1 && confirm "CocoaPods 캐시를 정리할까요?"; then
    pod cache clean --all
    rm -rf ~/Library/Caches/CocoaPods
fi

# 7. Docker
if command -v docker >/dev/null 2>&1; then
    section "7. Docker 정리"
    docker system df
    if confirm "사용하지 않는 Docker 컨테이너/이미지/볼륨을 모두 삭제할까요? (중요 볼륨 확인 필수)"; then
        docker system prune -af --volumes
    fi
fi

# 8. Time Machine 로컬 스냅샷
section "8. Time Machine 로컬 스냅샷"
tmutil listlocalsnapshots / 2>/dev/null
if confirm "로컬 스냅샷을 정리할까요?"; then
    sudo tmutil thinlocalsnapshots / 999999999999 4
fi

# 9. iOS/iPadOS 백업
section "9. iOS/iPadOS 기기 백업"
BACKUP_DIR=~/Library/Application\ Support/MobileSync/Backup
if [ -d "$BACKUP_DIR" ]; then
    ls -al "$BACKUP_DIR"
    if confirm "위 백업을 삭제할까요? (필요한 기기 백업이 없는지 확인하세요)"; then
        rm -rf "$BACKUP_DIR"/*
    fi
fi

# 10. 메일 다운로드 캐시
MAIL_DIR=~/Library/Containers/com.apple.mail/Data/Library/Mail\ Downloads
if [ -d "$MAIL_DIR" ]; then
    section "10. Mail 다운로드/첨부파일 캐시"
    if confirm "Mail 다운로드 캐시를 삭제할까요?"; then
        rm -rf "$MAIL_DIR"/*
    fi
fi

# 11. 휴지통
section "11. 휴지통 비우기"
if confirm "휴지통을 비울까요?"; then
    rm -rf ~/.Trash/*
    for trash in /Volumes/*/.Trashes; do
        [ -d "$trash" ] && sudo rm -rf "$trash"/*
    done
fi

echo
echo "정리 후 디스크 사용량:"
df -h /

echo
echo "상위 용량 디렉터리 확인 (참고용):"
sudo du -hd1 /System/Volumes/Data 2>/dev/null | sort -h | tail -20

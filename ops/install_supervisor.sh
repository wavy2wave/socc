#!/bin/bash
# Установить ANNA-супервизор как launchd-агент (стартует при логине, держится живым). L1 ранг 3.
# Операторское действие — ты запускаешь это осознанно (SOCC-закон: не скрытый демон).
set -e
PLIST="$HOME/SOCC/ops/com.socc.anna.supervisor.plist"
LABEL="com.socc.anna.supervisor"
chmod +x "$HOME/SOCC/ops/anna_keepawake.sh"

echo "→ bootstrap $LABEL в gui/$(id -u)"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
launchctl enable "gui/$(id -u)/$LABEL"
echo "✅ установлено. ANNA под надзором (Telegram SAFE-MODE + автономия)."
echo "   статус:  python3 scripts/anna_supervisor_v1.py --status"
echo "   стоп:    touch SYSTEM/ANNA_MVP/runtime/SUPERVISOR_STOP   (и launchctl bootout gui/$(id -u)/$LABEL)"
echo "   live:    добавь ANNA_LIVE=1 в .secrets/anna_telegram.env, чтобы снять SAFE-MODE (записи/CRM)"

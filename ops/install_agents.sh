#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════════════
# SOCC · установка ритма машины (launchd, macOS)
#
# Что делает: кладёт plist'ы в ~/Library/LaunchAgents и грузит их, чтобы СУХОЙ
#   автопилот ARBITER жил 3×/сут без оператора и переживал перезагрузку.
#
# ЗАКОНЫ (не нарушаются):
#   · агент зовёт ТОЛЬКО ymarket_autopilot_v1.py — у того ФИЗИЧЕСКИ нет --commit-пути
#   · секретов в plist нет: скрипт сам грузит их из gitignored mint/.env
#   · живой write (RUBICON) — только вручную, словом оператора, НИКОГДА из агента
#
# Диагностика 2026-09-16: plist'ы лежали в ~/Library/LaunchAgents, но launchctl
#   показывал их НЕЗАГРУЖЕННЫМИ → ритм держался «на честном слове» и не пережил
#   бы перезагрузку. Этот скрипт делает ритм воспроизводимым.
# ══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

SOCC_ROOT="${SOCC_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
AGENTS_DIR="$HOME/Library/LaunchAgents"
PY_BIN="${SOCC_PYTHON:-$SOCC_ROOT/.venv/bin/python}"

echo "SOCC_ROOT = $SOCC_ROOT"
echo "AGENTS    = $AGENTS_DIR"

# Интерпретатор: prefer venv photoforge (py3.13 + Pillow) → затем venv репо → затем python3
if [[ ! -x "$PY_BIN" ]]; then
  if [[ -x "$HOME/.venvs/photoforge/bin/python" ]]; then
    PY_BIN="$HOME/.venvs/photoforge/bin/python"
  else
    PY_BIN="$(command -v python3)"
  fi
fi
echo "PYTHON    = $PY_BIN"
echo

mkdir -p "$AGENTS_DIR"

# --- рендер plist из шаблона (пути подставляются под текущую машину) -----------
render_plist() {
  local label="$1" script="$2" extra_args="$3"
  local out="$AGENTS_DIR/$label.plist"
  cat > "$out" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<!-- SOCC · сгенерировано ops/install_agents.sh · $(date -u +%Y-%m-%dT%H:%M:%SZ)
     ЗАКОН: только СУХОЙ автопилот (0₽). У вызываемого скрипта нет --commit-пути. -->
<plist version="1.0">
<dict>
    <key>Label</key><string>$label</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY_BIN</string>
        <string>$SOCC_ROOT/$script</string>
$(for a in $extra_args; do echo "        <string>$a</string>"; done)
    </array>
    <key>WorkingDirectory</key><string>$SOCC_ROOT/scripts/mint/arbiter</string>
    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Hour</key><integer>8</integer><key>Minute</key><integer>7</integer></dict>
        <dict><key>Hour</key><integer>14</integer><key>Minute</key><integer>17</integer></dict>
        <dict><key>Hour</key><integer>20</integer><key>Minute</key><integer>47</integer></dict>
    </array>
    <key>RunAtLoad</key><false/>
    <key>StandardOutPath</key>
    <string>$SOCC_ROOT/MEMORY_WAVE/reports/mint/arbiter/${label}.out</string>
    <key>StandardErrorPath</key>
    <string>$SOCC_ROOT/MEMORY_WAVE/reports/mint/arbiter/${label}.err</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST
  echo "  ✓ $out"
}

render_plist com.socc.arbiter.daycycle.v1 scripts/mint/arbiter/ymarket_autopilot_v1.py "--head-source wb"

# --- загрузка -------------------------------------------------------------------
echo
for plist in "$AGENTS_DIR"/com.socc.*.plist; do
  label=$(basename "$plist" .plist)
  launchctl unload "$plist" 2>/dev/null || true
  if launchctl load "$plist" 2>/dev/null; then
    echo "  ✓ загружен $label"
  else
    echo "  ✗ НЕ загрузился $label (см. launchctl load $plist)"
  fi
done

echo
echo "=== проверка: что реально загружено ==="
# `launchctl list | grep` НЕНАДЁЖЕН: в неинтерактивной оболочке он может вернуть
# пусто для агента, который фактически active (проверено 2026-09-16: list пусто,
# а `launchctl print` показывает state=running, pid, runs=1). Вердикт берём из print.
any_loaded=0
for plist in "$AGENTS_DIR"/com.socc.*.plist; do
  label=$(basename "$plist" .plist)
  if info=$(launchctl print "gui/$(id -u)/$label" 2>/dev/null); then
    state=$(printf '%s' "$info" | awk -F'= ' '/^[[:space:]]*state =/{print $2; exit}')
    pid=$(printf '%s'  "$info" | awk -F'= ' '/^[[:space:]]*pid =/{print $2; exit}')
    runs=$(printf '%s' "$info" | awk -F'= ' '/^[[:space:]]*runs =/{print $2; exit}')
    echo "  ✓ $label  state=${state:-?} pid=${pid:--} runs=${runs:-0}"
    any_loaded=1
  else
    echo "  ✗ $label  НЕ зарегистрирован в launchd"
  fi
done
[[ $any_loaded -eq 0 ]] && echo "  (ничего не загрузилось)"
echo
echo "Готово. Ручной контрольный прогон (сухой, 0₽):"
echo "  launchctl kickstart -k gui/\$(id -u)/com.socc.arbiter.daycycle.v1"

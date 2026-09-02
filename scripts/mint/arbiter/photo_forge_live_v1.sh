#!/usr/bin/env bash
# ФОТО-КУЗНИЦА · РУЧНОЙ ЖИВОЙ ЗАПУСК под venv (PIL на борту → brand-lock verify_canon кусается).
#
# Зачем отдельный лаунчер: системный /opt/homebrew/bin/python3=3.14 БЕЗ Pillow → verify_canon
# спал бы (is_white_bg/_aspect_ok = None), а бронь ATLAS EDGE молча пропускала бы вне-канонный кадр.
# Теперь живой canon-форж без PIL ФИЗИЧЕСКИ отказывается тратить (гард в pf.forge, до сети). Этот
# скрипт всегда зовёт venv-python (там Pillow) и включает --canon → ручной путь к карточке идёт
# под бронёй, а не «на честном слове». Смена интерпретатора → PHOTOFORGE_VENV_PY=/путь $0 ...
#
# RUBICON цел: без --live всё равно dry (0₽). --canon добавляем в хвост; прочие флаги — как есть.
# Живой кадр (--live) тратит ₽/квоту провайдера — только по отмашке оператора.
#
#   Примеры:
#     ./photo_forge_live_v1.sh --demo                 # сухой прогон демо-товара под бронёй (0₽)
#     ./photo_forge_live_v1.sh --doctor               # паспорт готовности провайдера (0₽ зонд)
#     ./photo_forge_live_v1.sh --demo --live --json   # ЖИВОЙ кадр (₽) канон-приёмкой, отчёт JSON
set -euo pipefail

PYBIN="${PHOTOFORGE_VENV_PY:-/Users/wavysexy/.venvs/photoforge/bin/python}"
ORGAN_DIR="/Users/wavysexy/SOCC/scripts/mint/arbiter"
PIPELINE="$ORGAN_DIR/photo_pipeline_v1.py"

if [[ ! -x "$PYBIN" ]]; then
  echo "!! venv-python не найден: $PYBIN" >&2
  echo "   создай: python3.13 -m venv ~/.venvs/photoforge && ~/.venvs/photoforge/bin/pip install Pillow" >&2
  echo "   или переопредели путь:  PHOTOFORGE_VENV_PY=/путь/к/python $0 ..." >&2
  exit 1
fi

# Честная проверка: Pillow реально на борту? Если нет — предупреждаем, но НЕ врём: живой --canon
# всё равно откажется тратить вслепую (гард). 0₽, только import.
if ! "$PYBIN" -c "import PIL" >/dev/null 2>&1; then
  echo "⚠  в $PYBIN нет Pillow → verify_canon слеп; живой --canon честно откажется тратить (гард)." >&2
  echo "   поставь: $PYBIN -m pip install Pillow" >&2
fi

cd "$ORGAN_DIR"
# Заголовок — в stderr, чтобы stdout остался ЧИСТЫМ (--json пайпится без мусора).
echo "· интерпретатор: $PYBIN" >&2
echo "· орган:         $PIPELINE" >&2
echo "· бронь:         --canon ВКЛ (ATLAS EDGE: белый фон + 4:5)" >&2
echo >&2
exec "$PYBIN" "$PIPELINE" "$@" --canon

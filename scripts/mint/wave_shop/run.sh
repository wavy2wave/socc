#!/usr/bin/env bash
# WAVE SHOP — запуск «под ключ». Одна команда: ./run.sh
#
# Что делает:
#   1. Проверяет python3 и .env (токен бота).
#   2. Поднимает бота с АВТО-ПЕРЕЗАПУСКОМ: если процесс упадёт (не сетевой сбой,
#      а жёсткий крах), скрипт поднимет его снова через 3с. Сетевые сбои бот
#      переживает сам внутри цикла — сюда доходят только настоящие падения.
#   3. По желанию поднимает ШЛЮЗ (gateway) — если в .env задан WAVE_UPSTREAM_KEY.
#
# Остановить: Ctrl+C (гасит и бота, и шлюз).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null 2>&1 || { echo "❌ python3 не найден. Установите Python 3."; exit 1; }

if [[ ! -f .env ]]; then
  echo "❌ Нет .env. Скопируйте пример и впишите токен:"
  echo "     cp .env.example .env"
  echo "     # затем впишите WAVE_BOT_TOKEN и WAVE_ADMIN_IDS"
  exit 1
fi

# Токен обязателен — без него бот всё равно откажется стартовать, скажем сразу.
if ! grep -qE '^WAVE_BOT_TOKEN=.+' .env; then
  echo "❌ В .env не задан WAVE_BOT_TOKEN. Получите токен у @BotFather и впишите."
  exit 1
fi

GW_PID=""
BOT_PID=""

# Гасим ВСЮ группу процессов, а не только PID-ы, что мы поймали: под каждым
# supervisor-циклом крутится питон-ребёнок, и убить один цикл мало — осиротевший
# бот продолжил бы опрашивать Telegram. `kill 0` бьёт по группе (цикл + питон).
cleanup() {
  trap - INT TERM EXIT
  echo
  echo "🛑 Останавливаю WAVE SHOP (бот + шлюз)…"
  kill 0 2>/dev/null || true
}
trap cleanup INT TERM EXIT

# Один supervisor: перезапускает команду, пока её не остановят сигналом.
# Сетевые сбои процесс переживает сам внутри — сюда доходит только жёсткий крах.
supervise() {
  label="$1"; shift
  while true; do
    "$@" || true
    echo "⚠️  ${label} завершился. Перезапуск через 3с… (Ctrl+C чтобы выйти)"
    sleep 3
  done
}

# Шлюз поднимаем только если оператор реально дал топливо — и тоже под
# supervisor: раньше он запускался один раз и, упав, не поднимался, а бот
# продолжал работать как будто шлюз жив. Топливо = ЛЮБОЙ источник ключей:
# одиночный WAVE_UPSTREAM_KEY, список WAVE_UPSTREAM_KEYS или непустой файл
# обоймы (data/upstream_pool.keys — «дрова», дозаливаемые на лету). Считаем
# файл непустым, если в нём есть хоть одна строка не из # и не пустая.
POOL_FILE="${WAVE_UPSTREAM_POOL_FILE:-data/upstream_pool.keys}"
has_pool_keys() {
  [[ -f "$POOL_FILE" ]] && grep -qE '^[[:space:]]*[^#[:space:]]' "$POOL_FILE"
}

if grep -qE '^WAVE_UPSTREAM_KEY=.+' .env \
   || grep -qE '^WAVE_UPSTREAM_KEYS=.+' .env \
   || has_pool_keys; then
  echo "🔌 Топливо для шлюза найдено — поднимаю gateway с авто-перезапуском…"
  supervise "Шлюз" "$PY" -m gateway.proxy &
  GW_PID=$!
  sleep 1
else
  echo "ℹ️  Ключей апстрима нет (ни WAVE_UPSTREAM_KEY, ни ${POOL_FILE}) —"
  echo "    шлюз не запускаю (продаём обычные товары). Залей ключи в обойму,"
  echo "    чтобы поднять доступ к ИИ."
fi

echo "🌊 Запускаю бота с авто-перезапуском. Остановить: Ctrl+C (или kill / systemctl stop)."
supervise "Бот" "$PY" bot.py &
BOT_PID=$!

# Ждём в прерываемом wait: сигнал (Ctrl+C, kill, systemctl stop) тут же уводит
# в cleanup. Раньше бот крутился в foreground-цикле — trap откладывался до его
# выхода, и остановить магазин штатным сигналом было нельзя.
wait

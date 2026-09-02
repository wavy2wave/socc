"""WAVE GATEWAY — обойма сырых ключей провайдера («дрова»).

Зачем этот модуль. Раньше наверх ходил ОДИН ключ (WAVE_UPSTREAM_KEY). Когда у
него кончался баланс — падали ВСЕ клиенты разом, и оператор узнавал об этом от
злого друга, а не от системы. Обойма превращает один ключ в магазин патронов:
стреляем текущим, пока он не сдохнет, и в ствол автоматически встаёт следующий
живой. Список пополняется «дровами» — оператор дописывает ключи в файл в любой
момент, БЕЗ перезапуска шлюза.

Что важно понимать про разделение ответственности:
  • КВОТА/СРОК клиента живут на его токене wave-… (см. quota.py) и проверяются
    ДО обращения наверх. Обойма к квоте не относится — она про топливо.
  • Клиентский токен привязан к обойме В ЦЕЛОМ, а не к одному патрону: какой бы
    сырой ключ ни обслужил запрос, у клиента списывается один и тот же счётчик.

Политика (согласована с оператором):
  • 401 / 403  → патрон МЁРТВ навсегда (ключ отозван/невалиден). Ротируем и
                 больше к нему не возвращаемся. Смерть переживает рестарт
                 (хранится по отпечатку в data/upstream_pool_state.json).
  • 429        → патрон ВРЕМЕННО перегрет: cooldown 60с, потом снова годен.
                 Rate-limit ≠ пустой баланс — сжигать годный ключ нельзя.
  • прочее     → не про обойму (сбой провайдера/сети): наверх отдаётся как есть,
                 патрон не трогаем.

Отпечаток вместо ключа. Ни один сырой ключ не попадает в лог или в файл
состояния — только его короткий SHA-256-отпечаток (fp). Даже если файл
состояния утечёт, это набор хешей, а не ключи.

Канон MINT: stdlib-only, атомарная запись, потокобезопасно (шлюз многопоточный),
fail-soft (битый файл состояния не роняет шлюз).
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Callable

# Политика по умолчанию (переопределяется из окружения).
_DEFAULT_COOLDOWN_SEC = int(os.environ.get("WAVE_UPSTREAM_COOLDOWN_SEC", "60") or "60")
# Потолок попыток в рамках ОДНОГО запроса клиента. Если оператор высыпал сотню
# дохлых ключей, мы не должны перебирать всю сотню на каждый клиентский запрос —
# помечаем сколько успели, отдаём 503, а обойма самоочищается за следующие
# запросы (мёртвые патроны уже исключены). 0 => без ограничения (не рекомендуется).
_MAX_ATTEMPTS = int(os.environ.get("WAVE_UPSTREAM_MAX_ATTEMPTS", "8") or "8")

# Шапка авто-создаваемого файла обоймы — чтобы оператор сразу видел, куда лить.
_TEMPLATE = """# WAVE GATEWAY — обойма сырых ключей провайдера.
#
# По ОДНОМУ ключу в строке. Дозаливай в любой момент — новые строки
# подхватываются на лету, без перезапуска шлюза («дрова»).
#   • строки, начинающиеся с #, и пустые — игнорируются;
#   • дубликаты схлопываются;
#   • ключ, вернувший 401/403, помечается мёртвым и больше не используется
#     (даже если снова появится в файле — отпечаток запоминается).
#
# Файл лежит в data/ и уже в .gitignore — в git он НЕ попадёт.
#
# sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
# sk-yyyyyyyyyyyyyyyyyyyyyyyyyyyy
"""


def fingerprint(key: str) -> str:
    """Короткий необратимый отпечаток ключа для логов и файла состояния."""
    return hashlib.sha256((key or "").encode("utf-8")).hexdigest()[:12]


def _read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _parse_keys(text: str) -> list[str]:
    """Разобрать содержимое файла обоймы: по ключу в строке, # — комментарий."""
    out: list[str] = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        out.append(s)
    return out


class UpstreamPool:
    """Магазин сырых ключей со sticky-ротацией и живучестью смертей.

    Источники ключей (объединяются, порядок сохраняется, дубликаты схлопываются):
      1. файл обоймы (pool_file) — основной, дозаливаемый оператором;
      2. env WAVE_UPSTREAM_KEYS — список через запятую (стартовая засыпка);
      3. env WAVE_UPSTREAM_KEY — одиночный ключ (обратная совместимость).
    """

    def __init__(
        self,
        pool_file: Path,
        state_file: Path | None = None,
        env_keys: str = "",
        env_single: str = "",
        cooldown_sec: int = _DEFAULT_COOLDOWN_SEC,
        max_attempts: int = _MAX_ATTEMPTS,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self.pool_file = Path(pool_file)
        self.state_file = Path(state_file) if state_file else \
            self.pool_file.with_name("upstream_pool_state.json")
        self._env_keys = [k.strip() for k in (env_keys or "").split(",") if k.strip()]
        self._env_single = (env_single or "").strip()
        self.cooldown_sec = max(1, int(cooldown_sec))
        self.max_attempts = int(max_attempts)
        self._log = log or (lambda _m: None)

        self._lock = threading.RLock()
        self._keys: list[str] = []            # текущий порядок сырых ключей
        self._mtime: float = -1.0             # mtime файла на момент последней загрузки
        self._cursor: int = 0                 # sticky-указатель на текущий патрон
        self._cooldown: dict[str, float] = {}  # fp -> когда снова годен (epoch)
        self._dead: set[str] = set()          # fp мёртвых (401/403), переживает рестарт

        self._load_state()
        self._reload(force=True)

    # ---------- состояние (мёртвые патроны) ----------
    def _load_state(self) -> None:
        data = _read_json(self.state_file, {})
        if isinstance(data, dict):
            dead = data.get("dead", [])
            if isinstance(dead, list):
                self._dead = {str(x) for x in dead}

    def _save_state(self) -> None:
        try:
            _write_json(self.state_file, {"dead": sorted(self._dead)})
        except OSError as e:  # не роняем шлюз из-за диска
            self._log(f"обойма: не смог сохранить состояние: {type(e).__name__}")

    # ---------- загрузка ключей ----------
    def _sources(self) -> list[str]:
        keys: list[str] = []
        try:
            if self.pool_file.exists():
                keys.extend(_parse_keys(self.pool_file.read_text(encoding="utf-8")))
        except OSError:
            pass
        keys.extend(self._env_keys)
        if self._env_single:
            keys.append(self._env_single)
        # Схлопнуть дубликаты, сохранив порядок.
        seen: set[str] = set()
        uniq: list[str] = []
        for k in keys:
            if k and k not in seen:
                seen.add(k)
                uniq.append(k)
        return uniq

    def _file_mtime(self) -> float:
        try:
            return self.pool_file.stat().st_mtime
        except OSError:
            return -1.0

    def _reload(self, force: bool = False) -> None:
        """Перечитать источники, если файл изменился (или force). Держит замок."""
        mtime = self._file_mtime()
        if not force and mtime == self._mtime:
            return
        with self._lock:
            new_keys = self._sources()
            if new_keys != self._keys:
                added = [k for k in new_keys if k not in self._keys]
                removed = [k for k in self._keys if k not in new_keys]
                self._keys = new_keys
                # Курсор мог указывать за пределы после сжатия обоймы.
                if self._cursor >= len(self._keys):
                    self._cursor = 0
                if added:
                    self._log(f"обойма: +{len(added)} ключ(ей) "
                              f"({', '.join(fingerprint(k) for k in added)})")
                if removed:
                    self._log(f"обойма: −{len(removed)} ключ(ей) убрано из файла")
            self._mtime = mtime

    def ensure_template(self) -> None:
        """Создать файл-заглушку с шапкой, если обоймы ещё нет и env пуст.

        Вызывается из proxy.main(), а не из конструктора: у тестов свои временные
        каталоги, и побочная запись при импорте была бы сюрпризом.
        """
        if self.pool_file.exists() or self._env_keys or self._env_single:
            return
        try:
            self.pool_file.parent.mkdir(parents=True, exist_ok=True)
            self.pool_file.write_text(_TEMPLATE, encoding="utf-8")
            self._log(f"обойма: создан шаблон {self.pool_file} — впиши сырые ключи")
        except OSError:
            pass

    # ---------- выбор патрона ----------
    def _alive(self, key: str, now: float) -> bool:
        fp = fingerprint(key)
        if fp in self._dead:
            return False
        cd = self._cooldown.get(fp, 0.0)
        return now >= cd

    def pick(self, now: float | None = None) -> str | None:
        """Вернуть живой сырой ключ или None, если обойма пуста/вся недоступна.

        Sticky: держимся текущего патрона, пока он жив; при смерти/перегреве —
        первый живой начиная с курсора (курсор переезжает на него).
        """
        now = time.time() if now is None else now
        self._reload()
        with self._lock:
            n = len(self._keys)
            if n == 0:
                return None
            for step in range(n):
                idx = (self._cursor + step) % n
                key = self._keys[idx]
                if self._alive(key, now):
                    self._cursor = idx
                    return key
            return None

    # ---------- обратная связь после запроса ----------
    def mark_dead(self, key: str) -> None:
        """401/403: патрон мёртв навсегда. Курсор сдвинется на следующем pick()."""
        fp = fingerprint(key)
        with self._lock:
            if fp not in self._dead:
                self._dead.add(fp)
                self._save_state()
                self._log(f"обойма: патрон {fp} МЁРТВ (401/403) — исключён")

    def mark_cooldown(self, key: str, now: float | None = None,
                      seconds: int | None = None) -> None:
        """429: патрон перегрет, отдыхает cooldown_sec секунд."""
        now = time.time() if now is None else now
        secs = self.cooldown_sec if seconds is None else max(1, int(seconds))
        fp = fingerprint(key)
        with self._lock:
            self._cooldown[fp] = now + secs
            self._log(f"обойма: патрон {fp} на паузе {secs}с (429)")

    def report_ok(self, key: str) -> None:
        """Успешный ответ: снять возможную паузу (годен точно)."""
        fp = fingerprint(key)
        with self._lock:
            self._cooldown.pop(fp, None)

    # ---------- наблюдаемость ----------
    def has_capacity(self) -> bool:
        """Есть ли хоть один НЕ-мёртвый ключ (годный сейчас или после паузы)."""
        self._reload()
        with self._lock:
            return any(fingerprint(k) not in self._dead for k in self._keys)

    def stats(self, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        self._reload()
        with self._lock:
            total = len(self._keys)
            dead = sum(1 for k in self._keys if fingerprint(k) in self._dead)
            cooling = sum(1 for k in self._keys
                          if fingerprint(k) not in self._dead
                          and now < self._cooldown.get(fingerprint(k), 0.0))
            alive = total - dead - cooling
            return {"total": total, "alive": alive, "cooling": cooling, "dead": dead}

    def exhausted_reason(self, now: float | None = None) -> str:
        """Почему pick() вернул None: empty | all_dead | cooling."""
        s = self.stats(now)
        if s["total"] == 0:
            return "empty"
        if s["alive"] == 0 and s["cooling"] > 0:
            return "cooling"
        return "all_dead"


class NoCapacity(Exception):
    """Обойму нечем зарядить прямо сейчас: пусто, всё мертво или всё на паузе.

    Отдельный тип, чтобы вызывающий отдал клиенту 503 и — принципиально — НЕ
    списывал его квоту: раз наверх ничего не ушло, платить клиенту не за что.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def dispatch(pool: UpstreamPool, call_fn: Callable[[str], tuple],
             classify: Callable[[BaseException], str]) -> tuple:
    """Прогнать один запрос через обойму с ротацией — сердце failover.

    Вынесено сюда (а не в proxy) нарочно: так логику ротации можно проверить
    тестом с поддельным call_fn, без единого живого HTTP-запроса.

      call_fn(key)  -> (payload, status); может бросить исключение.
      classify(exc) -> 'dead' (патрон 401/403) | 'cooldown' (429) | 'raise'.

    Возвращает (payload, status) при успехе. Бросает NoCapacity, если обойма
    пуста/вся недоступна или исчерпан лимит попыток. Ошибку, которую classify
    отнёс к 'raise' (сбой провайдера/сети — не про обойму), пробрасывает как есть.
    """
    attempts = 0
    limit = pool.max_attempts
    while limit <= 0 or attempts < limit:
        key = pool.pick()
        if key is None:
            raise NoCapacity(pool.exhausted_reason())
        attempts += 1
        try:
            payload, status = call_fn(key)
        except BaseException as exc:  # noqa: BLE001 — решение отдаём classify
            verdict = classify(exc)
            if verdict == "dead":
                pool.mark_dead(key)
                continue
            if verdict == "cooldown":
                pool.mark_cooldown(key)
                continue
            raise
        else:
            pool.report_ok(key)
            return payload, status
    # Перебрали лимит патронов в рамках ОДНОГО запроса — не жжём остальные,
    # мёртвые уже помечены, обойма самоочистится к следующему запросу.
    raise NoCapacity("attempts_exhausted")

#!/usr/bin/env python3
"""
ANNA Supervisor V1 — watchdog that keeps ANNA alive for days (L1 «неубиваемость»).

A clinic's admin must NEVER stay dead. This supervisor keeps ANNA's processes
(Telegram bot, autonomy loop) running: if one dies it restarts it with exponential
backoff; if it crash-loops it quarantines it and alerts instead of hammering; it
periodically probes the brain with `anna_runtime_v1.py --health` and restarts a
service whose brain went unreachable.

SOCC law: this is NOT a hidden daemon. It is an EXPLICIT operator-started supervisor
with a STOP file — the operator knows it runs and can stop it cleanly. Two modes:
  loop  (default) — foreground supervisor, Ctrl-C or STOP file to end.
  --once          — one supervision pass then exit (for cron-driven supervision: even
                    more lawful — no persistent process, the OS scheduler is the heartbeat).

Config: SYSTEM/ANNA_MVP/runtime/supervisor.json (auto-seeded on first run; edit to taste).
Stop:   touch SYSTEM/ANNA_MVP/runtime/SUPERVISOR_STOP
Log:    SYSTEM/ANNA_MVP/runtime/supervisor.log
Alert:  optional, set ANNA_ADMIN_WEBHOOK to get notified on quarantine.

Usage:
  python3 scripts/anna_supervisor_v1.py            # foreground watchdog loop
  python3 scripts/anna_supervisor_v1.py --once     # single pass (cron)
  python3 scripts/anna_supervisor_v1.py --status    # print live status, do nothing
"""
import os, sys, json, time, signal, subprocess, urllib.request
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent  # SOCC/
RUNTIME = ROOT / "SYSTEM/ANNA_MVP/runtime"
CONFIG = RUNTIME / "supervisor.json"
STATE = RUNTIME / "supervisor_state.json"
STOP = RUNTIME / "SUPERVISOR_STOP"
LOG = RUNTIME / "supervisor.log"
PY = sys.executable or "python3"

# Crash-loop guard: more than N restarts inside WINDOW seconds → quarantine (stop hammering, alert).
CRASHLOOP_N = int(os.environ.get("ANNA_CRASHLOOP_N", "5"))
CRASHLOOP_WINDOW_S = int(os.environ.get("ANNA_CRASHLOOP_WINDOW_S", "120"))
BACKOFF_BASE_S = float(os.environ.get("ANNA_BACKOFF_BASE_S", "2"))
BACKOFF_MAX_S = float(os.environ.get("ANNA_BACKOFF_MAX_S", "60"))
HEALTH_EVERY_S = int(os.environ.get("ANNA_HEALTH_EVERY_S", "180"))   # brain probe cadence
TICK_S = float(os.environ.get("ANNA_SUPERVISOR_TICK_S", "5"))


def now():
    return datetime.now(timezone.utc).isoformat()


def log(msg):
    line = f"{now()}  {msg}"
    print(line, flush=True)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def alert(text):
    hook = os.environ.get("ANNA_ADMIN_WEBHOOK")
    if not hook:
        return
    try:
        body = json.dumps({"text": "🛟 ANNA supervisor: " + text}).encode()
        req = urllib.request.Request(hook, data=body, method="POST")
        req.add_header("content-type", "application/json")
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


DEFAULT_CONFIG = {
    "note": "Сервисы ANNA под надзором. cmd — список аргументов; health_cmd (опц.) — проба, "
            "ненулевой код = перезапуск сервиса. enabled=false чтобы временно снять с надзора.",
    "services": [
        {
            "name": "telegram",
            "enabled": False,
            "cmd": [PY, "scripts/anna_telegram_v1.py"],
            "cwd": str(ROOT),
            "health_cmd": [PY, "scripts/anna_runtime_v1.py", "--health"],
            "health_fail_limit": 2
        },
        {
            "name": "autonomy",
            "enabled": False,
            "cmd": [PY, "scripts/anna_autonomy_v1.py"],
            "cwd": str(ROOT),
            "health_cmd": None,
            "health_fail_limit": 3
        }
    ]
}


def load_config():
    if not CONFIG.exists():
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2))
        log(f"seeded default config → {CONFIG} (services disabled by default; enable when ready)")
    return json.loads(CONFIG.read_text())


def save_state(state):
    tmp = STATE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    tmp.replace(STATE)   # atomic: a crash mid-write never corrupts state


def load_state():
    if STATE.exists():
        try:
            return json.loads(STATE.read_text())
        except Exception:
            pass
    return {"services": {}}


def alive(proc):
    return proc is not None and proc.poll() is None


def health_ok(svc):
    hc = svc.get("health_cmd")
    if not hc:
        return True
    try:
        r = subprocess.run(hc, cwd=svc.get("cwd") or str(ROOT),
                           capture_output=True, text=True, timeout=120)
        return r.returncode == 0
    except Exception:
        return False


class Service:
    def __init__(self, spec, st):
        self.spec = spec
        self.name = spec["name"]
        self.proc = None
        self.restarts = st.get("restarts", [])     # epoch list, for crashloop window
        self.health_fails = 0
        self.next_start = 0.0                       # backoff gate
        self.backoff = BACKOFF_BASE_S
        self.quarantined = st.get("quarantined", False)
        self.last_health = 0.0

    def _recent_restarts(self):
        cut = time.time() - CRASHLOOP_WINDOW_S
        self.restarts = [t for t in self.restarts if t >= cut]
        return len(self.restarts)

    def start(self):
        if self.quarantined:
            return
        if time.time() < self.next_start:
            return
        try:
            self.proc = subprocess.Popen(self.spec["cmd"], cwd=self.spec.get("cwd") or str(ROOT))
            self.restarts.append(time.time())
            log(f"[{self.name}] started pid {self.proc.pid} (cmd={' '.join(self.spec['cmd'])})")
        except Exception as e:
            log(f"[{self.name}] FAILED to start: {e}")
            self.next_start = time.time() + self.backoff
            self.backoff = min(BACKOFF_MAX_S, self.backoff * 2)
            return
        if self._recent_restarts() > CRASHLOOP_N:
            self.quarantined = True
            log(f"[{self.name}] 🚨 CRASH-LOOP ({self._recent_restarts()} restarts/{CRASHLOOP_WINDOW_S}s) → QUARANTINE")
            alert(f"{self.name} crash-loops, quarantined — нужен ручной разбор")

    def supervise_once(self, do_health):
        """One pass: ensure running; restart dead with backoff; probe brain health."""
        if self.quarantined:
            return
        if not alive(self.proc):
            if self.proc is not None:
                code = self.proc.returncode
                log(f"[{self.name}] died (exit {code}) → restarting with backoff {self.backoff:.0f}s")
                self.next_start = time.time() + self.backoff
                self.backoff = min(BACKOFF_MAX_S, self.backoff * 2)
                self.proc = None
            self.start()
            return
        # alive → reset backoff and optionally probe the brain
        self.backoff = BACKOFF_BASE_S
        if do_health and (time.time() - self.last_health) >= HEALTH_EVERY_S:
            self.last_health = time.time()
            if health_ok(self.spec):
                self.health_fails = 0
            else:
                self.health_fails += 1
                log(f"[{self.name}] brain health FAIL {self.health_fails}/{self.spec.get('health_fail_limit', 2)}")
                if self.health_fails >= self.spec.get("health_fail_limit", 2):
                    log(f"[{self.name}] brain unreachable → restarting service")
                    alert(f"{self.name}: мозг недоступен, перезапускаю")
                    self.stop()
                    self.health_fails = 0

    def stop(self):
        if alive(self.proc):
            try:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=8)
                except Exception:
                    self.proc.kill()
            except Exception:
                pass
        self.proc = None

    def export(self):
        return {"restarts": self.restarts, "quarantined": self.quarantined,
                "pid": self.proc.pid if alive(self.proc) else None,
                "health_fails": self.health_fails}


def run(once=False):
    cfg = load_config()
    st = load_state()
    services = [Service(s, st["services"].get(s["name"], {}))
                for s in cfg.get("services", []) if s.get("enabled")]
    if not services:
        log("нет включённых сервисов в supervisor.json (enabled=true чтобы взять под надзор). Выхожу.")
        return
    stopping = {"v": False}

    def _sig(*_):
        stopping["v"] = True
    signal.signal(signal.SIGINT, _sig)
    signal.signal(signal.SIGTERM, _sig)

    log(f"supervisor {'(--once)' if once else 'loop'} взял под надзор: {[s.name for s in services]}")
    while True:
        if STOP.exists():
            log("найден SUPERVISOR_STOP → останавливаю сервисы и выхожу (операторский стоп)")
            for s in services:
                s.stop()
            break
        for s in services:
            s.supervise_once(do_health=True)
        st = {"ts": now(), "services": {s.name: s.export() for s in services}}
        save_state(st)
        if once or stopping["v"]:
            if stopping["v"]:
                log("сигнал остановки → глушу сервисы")
                for s in services:
                    s.stop()
            break
        time.sleep(TICK_S)


def status():
    st = load_state()
    print(f"📡 ANNA supervisor — {st.get('ts', 'нет состояния')}")
    for name, s in (st.get("services") or {}).items():
        mark = "🚨quarantine" if s.get("quarantined") else ("🟢" if s.get("pid") else "⚪")
        print(f"  {mark} {name}: pid={s.get('pid')} restarts(window)={len(s.get('restarts', []))} "
              f"health_fails={s.get('health_fails', 0)}")
    print(f"STOP-файл: {'есть (надзор остановлен)' if STOP.exists() else 'нет'}")


def main():
    args = sys.argv[1:]
    if "--status" in args:
        status(); return
    run(once="--once" in args)


if __name__ == "__main__":
    main()

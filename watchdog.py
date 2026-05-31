#!/usr/bin/env python3
"""watchdog.py — keep-alive do scan unificado de selados (autonomia).

Pensado pra rodar pelo Windows Task Scheduler a cada 15 min. Garante que o
scan unificado (run_all_sources.py) esteja SEMPRE rodando ou recém-concluído,
e RESSUSCITA o processo se ele morreu.

Lógica por tick (15 min):
  1. Lê o lockfile. Se há um run em andamento (PID vivo e lock não-velho):
     loga "já rodando" e sai. (Evita empilhar runs e colisão do perfil Chrome
     headful da Liga.)
  2. Se o lock está velho/morto (processo caiu, travou > MAX_RUNTIME): considera
     MORTO, limpa o lock e RELANÇA — é a "ressurreição".
  3. Se não há run e o último resultado é mais velho que REFRESH_MIN (ou não
     existe): atualiza os preços US se estiverem velhos (>US_REFRESH_HOURS) e
     LANÇA um novo scan unificado.
  4. Caso contrário (resultado fresco e nada rodando): não faz nada.

O refresh dos preços US (build_us_reference.py) roda ANTES do scan, no máximo
~1x/dia (gate US_REFRESH_HOURS), pra que as margens nunca usem preço velho. É
não-fatal: se falhar, o scan segue com a referência que existir.

Tudo é logado em watchdog.log (rolling) e cada run tem seu próprio log em
results/unified_<ts>/run.log. Falhas nunca propagam pro Task Scheduler como
erro fatal — o próximo tick tenta de novo.

Uso:
    python watchdog.py            # tick normal (chamado pelo Task Scheduler)
    python watchdog.py --force    # força um novo run agora (ignora REFRESH)
    python watchdog.py --status   # imprime estado e sai
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
LOCK = SCRIPT_DIR / ".watchdog.lock"
LOG = SCRIPT_DIR / "watchdog.log"
RESULTS = SCRIPT_DIR / "results"
US_REFERENCE = SCRIPT_DIR / "data" / "us_reference.json"

REFRESH_MIN = 45        # relança se o último sucesso for mais velho que isso
MAX_RUNTIME_MIN = 70    # se um run passar disso, é considerado travado → mata+relança
US_REFRESH_HOURS = 20   # atualiza preços US (build_us_reference) no máx ~1x/dia, antes do scan
US_REFRESH_TIMEOUT_S = 300  # teto pro refresh de preços US (tcgcsv costuma levar <60s)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def log(msg: str) -> None:
    line = f"[{_now().isoformat(timespec='seconds')}] {msg}"
    print(line)
    try:
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    """True se o PID existe (Windows: via tasklist)."""
    if pid <= 0:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=15,
        ).stdout
        return str(pid) in out
    except Exception:
        return False


def _read_lock() -> dict | None:
    if not LOCK.exists():
        return None
    try:
        parts = dict(
            line.split("=", 1)
            for line in LOCK.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        pid = int(parts.get("pid", "0"))
        # scan_pid = PID do subprocess run_all_sources.py (o que de fato
        # segura o Chrome da Liga). Lock de formato antigo não tem → cai no pid.
        scan_pid = int(parts.get("scan_pid", "0")) or pid
        return {
            "pid": pid,
            "scan_pid": scan_pid,
            "started": float(parts.get("started", "0")),
        }
    except Exception:
        return None


def _acquire_lock() -> bool:
    """Cria o lock ATOMICAMENTE (O_EXCL). Retorna False se já existe — fecha a
    janela TOCTOU entre dois ticks concorrentes (wake-from-sleep catch-up)."""
    try:
        fd = os.open(str(LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False  # outro tick segura o lock
    except OSError as exc:
        # permissão / disco / antivírus segurando o handle: não adquire agora,
        # tenta de novo no próximo tick (15min). Loga em vez de derrubar o tick.
        log(f"_acquire_lock falhou ({type(exc).__name__}: {exc}) — skip este tick")
        return False
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(f"pid={os.getpid()}\nscan_pid=0\nstarted={time.time()}\n")
    return True


def _set_scan_pid(scan_pid: int) -> None:
    """Atualiza o lock com o PID do subprocess de scan (preserva started)."""
    lk = _read_lock()
    started = lk["started"] if lk else time.time()
    LOCK.write_text(
        f"pid={os.getpid()}\nscan_pid={scan_pid}\nstarted={started}\n",
        encoding="utf-8",
    )


def _clear_lock() -> None:
    try:
        LOCK.unlink()
    except OSError:
        pass


def _latest_unified() -> Path | None:
    if not RESULTS.exists():
        return None
    dirs = sorted(
        (d for d in RESULTS.glob("unified_*") if d.is_dir()),
        key=lambda d: d.stat().st_mtime, reverse=True,
    )
    return dirs[0] if dirs else None


def _last_success_age_min() -> float | None:
    """Idade (min) do último unified_deals.csv não-vazio. None se não há."""
    latest = _latest_unified()
    if not latest:
        return None
    csv = latest / "unified_deals.csv"
    if not csv.exists() or csv.stat().st_size < 50:  # só header = vazio
        return None
    return (time.time() - csv.stat().st_mtime) / 60.0


def _kill_pid(pid: int) -> None:
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=30)
    except Exception:
        pass


def _us_reference_age_hours() -> float | None:
    """Idade (horas) da referência US, pelo `captured_at` interno; mtime do
    arquivo como fallback. None se a referência não existe."""
    if not US_REFERENCE.exists():
        return None
    try:
        cap = json.loads(US_REFERENCE.read_text(encoding="utf-8")).get("captured_at")
        if cap:
            ts = datetime.fromisoformat(str(cap).replace("Z", "+00:00"))
            return (_now() - ts).total_seconds() / 3600.0
    except Exception:
        pass  # JSON corrompido / sem captured_at → cai no mtime
    return (time.time() - US_REFERENCE.stat().st_mtime) / 3600.0


def _maybe_refresh_us_reference() -> None:
    """Atualiza os preços US (build_us_reference.py) se a referência estiver mais
    velha que US_REFRESH_HOURS — roda ANTES do scan pra que as margens usem preço
    fresco. Falha é NÃO-FATAL: loga e segue com a referência atual (margem velha
    é melhor que scan abortado). Já está sob o lock do tick, então não corre com
    outro refresh."""
    age = _us_reference_age_hours()
    if age is not None and age < US_REFRESH_HOURS:
        return
    why = "ausente" if age is None else f"{age:.1f}h (>= {US_REFRESH_HOURS}h)"
    log(f"referência US {why} — atualizando preços (build_us_reference.py)")
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    try:
        r = subprocess.run(
            [sys.executable, str(SCRIPT_DIR / "build_us_reference.py")],
            cwd=str(SCRIPT_DIR), env=env,
            capture_output=True, text=True, timeout=US_REFRESH_TIMEOUT_S,
        )
        tail = "\n".join((r.stdout or "").splitlines()[-2:])
        log(f"referência US atualizada exit={r.returncode}\n{tail}")
    except subprocess.TimeoutExpired:
        log(f"referência US: build_us_reference ESTOUROU {US_REFRESH_TIMEOUT_S}s — segue com a atual")
    except Exception as exc:
        log(f"referência US: falhou ({type(exc).__name__}: {exc}) — segue com a atual")


def _launch_scan() -> int:
    """Roda run_all_sources.py. O lock JÁ foi adquirido atomicamente por tick().
    Grava o PID do subprocess no lock (pra ressurreição correta) e limpa no fim.
    Descobre o out_dir pelo marcador UNIFIED_OUT_DIR= no stdout (não por heurística
    de 'dir mais novo', que erra sob escrita concorrente)."""
    log(f"LANÇANDO scan unificado (watchdog pid={os.getpid()})")
    _maybe_refresh_us_reference()  # preços US frescos antes do scan (~1x/dia, não-fatal)
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(SCRIPT_DIR / "run_all_sources.py")],
            cwd=str(SCRIPT_DIR), env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        _set_scan_pid(proc.pid)
        log(f"scan rodando (subprocess pid={proc.pid})")
        try:
            stdout, stderr = proc.communicate(timeout=MAX_RUNTIME_MIN * 60)
        except subprocess.TimeoutExpired:
            log(f"scan ESTOUROU {MAX_RUNTIME_MIN}min (pid={proc.pid}) — matando árvore")
            _kill_pid(proc.pid)
            return 124
        # out_dir pelo marcador explícito; fallback heurístico só se faltar
        out_dir = None
        for line in (stdout or "").splitlines():
            if line.startswith("UNIFIED_OUT_DIR="):
                out_dir = Path(line.split("=", 1)[1].strip())
        if out_dir is None or not out_dir.exists():
            out_dir = _latest_unified()
        if out_dir and out_dir.exists():
            (out_dir / "run.log").write_text(
                (stdout or "") + "\n--- STDERR ---\n" + (stderr or ""),
                encoding="utf-8",
            )
        tail = "\n".join((stdout or "").splitlines()[-6:])
        log(f"scan terminou exit={proc.returncode}\n{tail}")
        return proc.returncode
    except Exception as exc:
        log(f"scan FALHOU ao lançar: {type(exc).__name__}: {exc}")
        if proc is not None and proc.poll() is None:
            _kill_pid(proc.pid)
        return 1
    finally:
        _clear_lock()


def _print_status() -> None:
    lk = _read_lock()
    age = _last_success_age_min()
    print("=== watchdog status ===")
    if lk:
        alive = _pid_alive(lk["scan_pid"])
        run_min = (time.time() - lk["started"]) / 60.0
        print(f"  lock: scan_pid={lk['scan_pid']} (watchdog {lk['pid']}) "
              f"alive={alive} rodando há {run_min:.1f}min")
    else:
        print("  lock: nenhum (nada rodando)")
    print(f"  último sucesso: {f'{age:.1f}min atrás' if age is not None else 'nenhum'}")
    latest = _latest_unified()
    print(f"  último dir: {latest if latest else '(nenhum)'}")


def tick(force: bool) -> int:
    lk = _read_lock()
    if lk:
        run_min = (time.time() - lk["started"]) / 60.0
        scan_pid = lk["scan_pid"]
        # "rodando" = o SUBPROCESS de scan está vivo (não o watchdog que o lançou).
        # Isto evita relançar quando o watchdog morreu mas o scan + Chrome seguem.
        if _pid_alive(scan_pid) and run_min < MAX_RUNTIME_MIN:
            log(f"já rodando (scan pid={scan_pid}, há {run_min:.1f}min) — skip")
            return 0
        # lock órfão (scan morto) ou travado (>MAX_RUNTIME) → ressuscita
        log(f"lock ÓRFÃO/TRAVADO (scan pid={scan_pid} alive={_pid_alive(scan_pid)} "
            f"há {run_min:.1f}min) — matando resíduo e limpando")
        if _pid_alive(scan_pid):
            _kill_pid(scan_pid)
        _clear_lock()

    age = _last_success_age_min()
    if not (force or age is None or age >= REFRESH_MIN):
        log(f"resultado fresco ({age:.0f}min < {REFRESH_MIN}min) e nada rodando — nada a fazer")
        return 0

    # aquisição ATÔMICA — se outro tick concorrente venceu a corrida, desiste
    # (fecha a janela TOCTOU de double-launch no wake-from-sleep).
    if not _acquire_lock():
        log("outro tick adquiriu o lock primeiro — skip")
        return 0
    why = "force" if force else ("sem resultado" if age is None else f"stale {age:.0f}min")
    log(f"decisão: LANÇAR ({why})")
    return _launch_scan()


def main() -> None:
    p = argparse.ArgumentParser(description="Watchdog keep-alive do scan unificado de selados")
    p.add_argument("--force", action="store_true", help="força um novo run agora")
    p.add_argument("--status", action="store_true", help="imprime estado e sai")
    args = p.parse_args()
    if args.status:
        _print_status()
        return
    sys.exit(tick(force=args.force))


if __name__ == "__main__":
    main()

"""lib/tcgcsv_history.py — histórico REAL de preço TCGPlayer (arquivo tcgcsv.com).

Port de `pokemon-longterm-outlook/outlook/pricehistory.py` (precedente da frota:
código é COPIADO/adaptado entre repos, nunca importado — mesmo caso do
lib/ebay_client.py). Três adaptações para este repo:
  1. stdlib `urllib` no lugar de `requests` (nenhuma dependência HTTP nova);
  2. categoria PARAMETRIZADA (Pokémon = "3", One Piece = "68") — sem hardcode;
  3. cache em disco injetável (default `data/cache/tcgcsv_history/`).

O tcgcsv.com arquiva snapshots DIÁRIOS do preço do TCGPlayer desde 2024-02-08
(`prices-YYYY-MM-DD.ppmd.7z`). Aqui baixamos datas de referência, extraímos a
categoria pedida e devolvemos `{productId: marketPrice}` — casamento
determinístico por `tcgplayer_product_id` do registry (nunca fuzzy). Uso neste
repo: SÓ para os productIds de SELADOS do registry (+ chases como indicador
auxiliar de demanda) — a análise é de selados, nunca de cartas avulsas.

Honestidade (regras duras da frota):
  - Sem `py7zr` instalado → retorno None e o caller degrada pra `n/d`; a run
    NUNCA quebra por isso.
  - Data fora do arquivo / download falhou / 7z corrompido → ponto pulado,
    nunca preço inventado.
  - Assinatura 7z validada ANTES de cachear (challenge/HTML servido com
    HTTP 200 não envenena o cache).
"""
from __future__ import annotations

import json
import shutil
import tempfile
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Optional

ARCHIVE_URL = "https://tcgcsv.com/archive/tcgplayer/prices-{d}.ppmd.7z"
HEADERS = {"User-Agent": "sealed-scanner/1.0"}   # User-Agent é obrigatório no tcgcsv
EARLIEST = date(2024, 2, 8)                      # início do arquivo (FAQ do tcgcsv)
TIMEOUT_S = 60
DEFAULT_WINDOWS = (30, 90, 180)
MAGIC_7Z = b"7z\xbc\xaf\x27\x1c"                 # rejeita HTML-200/corpo truncado

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "tcgcsv_history"


def _py7zr():
    try:
        import py7zr  # import local proposital: dependência opcional
        return py7zr
    except ImportError:
        return None


def py7zr_available() -> bool:
    return _py7zr() is not None


# --------------------------------------------------------------------------- #
# Datas de referência
# --------------------------------------------------------------------------- #
def target_dates(today: date,
                 windows: tuple[int, ...] = DEFAULT_WINDOWS) -> dict[int, date]:
    """{janela_em_dias: data_alvo}, clampado a >= EARLIEST e < hoje."""
    out: dict[int, date] = {}
    for w in windows:
        d = today - timedelta(days=w)
        if d < EARLIEST or d >= today:
            continue
        out[w] = d
    return out


# --------------------------------------------------------------------------- #
# Download + extração (com cache em disco)
# --------------------------------------------------------------------------- #
def _archive_path(d: date, cache_dir: Path) -> Path:
    return cache_dir / f"prices-{d.isoformat()}.ppmd.7z"


def _map_path(d: date, category_id: str, cache_dir: Path) -> Path:
    return cache_dir / f"cat{category_id}-{d.isoformat()}.json"


def _download(d: date, cache_dir: Path) -> Optional[Path]:
    """Baixa o `.7z` do dia (cacheado). 404/erro/corpo-não-7z → None."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    ap = _archive_path(d, cache_dir)
    if ap.exists() and ap.stat().st_size > 0:
        return ap
    req = urllib.request.Request(ARCHIVE_URL.format(d=d.isoformat()), headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            content = resp.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None
    if not content or not content.startswith(MAGIC_7Z):
        return None  # corpo não é um 7z (página de erro/challenge servida como 200)
    ap.write_bytes(content)
    return ap


def _best_market_from_rows(rows: list[dict]) -> dict[str, float]:
    """{productId(str): maior `marketPrice` não-reverse} — mesma regra do live
    (build_us_reference lê subTypeName Normal; aqui espelhamos a regra do
    outlook: ignora Reverse Holofoil e fica com o maior market por produto —
    para SELADO só existe a variante Normal, então as regras coincidem)."""
    best: dict[str, float] = {}
    for r in rows:
        if "reverse" in (r.get("subTypeName") or "").lower():
            continue
        m = r.get("marketPrice")
        if isinstance(m, (int, float)) and m > 0:
            pid = str(r.get("productId"))
            if m > best.get(pid, 0.0):
                best[pid] = float(m)
    return best


def _map_from_extracted(root: Path, category_id: str) -> dict[str, float]:
    """Varre `<root>/<data>/<cat>/<group>/prices` → {productId: market}."""
    out: dict[str, float] = {}
    for fp in root.rglob("prices"):
        parts = fp.parts
        if len(parts) >= 3 and parts[-3] == category_id:
            try:
                obj = json.loads(fp.read_text())
            except (ValueError, OSError):
                continue
            out.update(_best_market_from_rows(obj.get("results", [])))
    return out


def _extract_cat_map(archive: Path, category_id: str) -> dict[str, float]:
    """Extrai só os `prices` da categoria pedida do `.7z`."""
    py7zr = _py7zr()
    if py7zr is None:
        raise RuntimeError("py7zr ausente")
    with py7zr.SevenZipFile(archive, "r") as z:
        names = z.getnames()
    targets = [n for n in names
               if n.split("/")[1:2] == [category_id] and n.endswith("/prices")]
    if not targets:
        return {}
    tmp = Path(tempfile.mkdtemp(prefix="tcgcsv_hist_"))
    try:
        with py7zr.SevenZipFile(archive, "r") as z:
            z.extract(path=str(tmp), targets=targets)
        return _map_from_extracted(tmp, category_id)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def price_map_for_date(d: date, category_id: str = "3",
                       cache_dir: Path | None = None) -> Optional[dict[str, float]]:
    """{productId: market} pra um dia. Usa cache JSON; None se indisponível.

    Tenta o dia e até 2 dias anteriores (o arquivo às vezes pula um dia).
    Retorna None tanto quando `py7zr` falta quanto quando não há arquivo.
    """
    cache_dir = cache_dir or DEFAULT_CACHE_DIR
    for back in (0, 1, 2):
        dd = d - timedelta(days=back)
        if dd < EARLIEST:
            break
        mp = _map_path(dd, category_id, cache_dir)
        if mp.exists():
            try:
                return json.loads(mp.read_text())
            except ValueError:
                pass  # cache corrompido → re-extrai
        ap = _download(dd, cache_dir)
        if ap is None:
            continue
        try:
            m = _extract_cat_map(ap, category_id)
        except RuntimeError:        # py7zr ausente — não adianta tentar outro dia
            return None
        except Exception:           # 7z corrompido/truncado (Bad7zFile/LZMAError/EOFError)
            ap.unlink(missing_ok=True)   # remove o cache envenenado p/ re-download
            continue                # NUNCA estoura a run — degrada pra "n/d"
        if m:
            cache_dir.mkdir(parents=True, exist_ok=True)
            mp.write_text(json.dumps(m))
            return m
    return None


def build_price_maps(today: date,
                     windows: tuple[int, ...] = DEFAULT_WINDOWS,
                     category_id: str = "3",
                     cache_dir: Path | None = None,
                     log: Callable[[str], None] = lambda _s: None
                     ) -> dict[int, dict[str, float]]:
    """{janela: {productId: preço}} pros pontos de referência disponíveis."""
    maps: dict[int, dict[str, float]] = {}
    for w, d in target_dates(today, windows).items():
        m = price_map_for_date(d, category_id, cache_dir)
        if m:
            maps[w] = m
            log(f"  histórico {w}d ({d.isoformat()}): {len(m)} preços")
        else:
            log(f"  histórico {w}d ({d.isoformat()}): indisponível")
    return maps


def pct_changes(product_id: str, today_price: float,
                maps: dict[int, dict[str, float]]) -> dict[int, float]:
    """{janela: variação FRACIONÁRIA} pros pontos onde o produto tem preço.

    Ex.: {30: 0.02, 90: 0.11}. Janela sem preço pro produto = ausente do dict
    (nunca inventada). `today_price` <= 0 → dict vazio.
    """
    out: dict[int, float] = {}
    if not today_price or today_price <= 0:
        return out
    for w, m in maps.items():
        old = m.get(str(product_id))
        if old and old > 0:
            out[w] = (today_price - old) / old
    return out

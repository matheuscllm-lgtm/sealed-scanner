"""lib/analysis/market_intel.py — inteligência de mercado US (best-effort).

Coleta CANDIDATOS a evento de reprint/restock/nova onda a partir de feeds
públicos de notícias (RSS/Atom — ex.: PokéBeach, PokeGuardian; configurados em
`analysis.market_intel.feeds`), casando manchetes com os sets do registry.

Regras duras:
  - candidato NUNCA vira evento sozinho: vai pra `data/history/
    market_intel_<jogo>.jsonl` para CURADORIA (operador ou sessão do agente,
    que complementa com pesquisa dirigida) — só `scripts/import_events.py`
    promove a evento, sempre com source_url + data;
  - notícia = no MÁXIMO SINAL_DE_MERCADO; fórum/social = RUMOR;
  - falha de rede/parse = aviso e segue (nunca crash, nunca inventa);
  - sem scraping agressivo: só feeds públicos, 1 GET por feed;
  - GTS/Southern Hobby e estoque de varejistas exigem conta/anti-bot →
    fase 2; enquanto isso entram por import manual (import_events).
"""
from __future__ import annotations

import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HEADERS = {"User-Agent": "sealed-scanner/1.0 (market intel, low volume)"}
TIMEOUT_S = 30
# Palavras-gatilho de evento (EN — os feeds são do mercado US).
TRIGGER_WORDS = ("reprint", "restock", "print run", "wave", "back in stock",
                 "out of print", "allocation", "preorder", "pre-order",
                 "special set", "returning to")


def fetch_feed(url: str, opener=None) -> bytes | None:
    """GET simples do feed. None em qualquer falha (best-effort)."""
    open_fn = opener or urllib.request.urlopen
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with open_fn(req, timeout=TIMEOUT_S) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError, ValueError):
        return None


def parse_feed(content: bytes) -> list[dict]:
    """Itens de um RSS/Atom: [{title, link, published}]. Tolerante a lixo."""
    try:
        root = ET.fromstring(content)
    except ET.ParseError:
        return []
    items: list[dict] = []
    # RSS 2.0
    for it in root.iter("item"):
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "published": (it.findtext("pubDate") or "").strip(),
        })
    # Atom
    ns = "{http://www.w3.org/2005/Atom}"
    for it in root.iter(f"{ns}entry"):
        link = ""
        ln = it.find(f"{ns}link")
        if ln is not None:
            link = ln.get("href") or ""
        items.append({
            "title": (it.findtext(f"{ns}title") or "").strip(),
            "link": link.strip(),
            "published": (it.findtext(f"{ns}updated") or "").strip(),
        })
    return [i for i in items if i["title"]]


def match_candidates(items: list[dict], set_names: dict[str, str],
                     feed: dict, collected_at: str) -> list[dict]:
    """Manchetes com palavra-gatilho + nome de set do registry → candidatos.

    `set_names` = {set_code: set_name_EN}. Classificação sugerida vem do feed
    (`classification`, capada em SINAL_DE_MERCADO; forum → RUMOR).
    """
    cls = str(feed.get("classification") or "SINAL_DE_MERCADO")
    if feed.get("source_type") == "forum" or cls == "CONFIRMADA":
        cls = "RUMOR" if feed.get("source_type") == "forum" else "SINAL_DE_MERCADO"
    out: list[dict] = []
    for it in items:
        low = it["title"].lower()
        if not any(w in low for w in TRIGGER_WORDS):
            continue
        matched = [code for code, name in set_names.items()
                   if name and name.lower() in low]
        out.append({
            "source_type": feed.get("source_type") or "news",
            "feed": feed.get("name") or "",
            "title": it["title"],
            "source_url": it["link"],
            "published": it["published"],
            "matched_set_codes": matched,
            "classification_suggested": cls,
            "collected_at": collected_at,
        })
    return out


def collect(feeds: list[dict], set_names: dict[str, str], collected_at: str,
            opener=None, log=print) -> list[dict]:
    """Roda todos os feeds configurados. Best-effort: feed que falhar é
    avisado e pulado; retorna a lista de candidatos (dedupe pelo caller)."""
    candidates: list[dict] = []
    for feed in feeds or []:
        url = feed.get("url")
        if not url:
            continue
        content = fetch_feed(url, opener=opener)
        if content is None:
            log(f"  [intel] feed indisponível: {feed.get('name') or url} — pulado (best-effort)")
            continue
        items = parse_feed(content)
        found = match_candidates(items, set_names, feed, collected_at)
        log(f"  [intel] {feed.get('name') or url}: {len(items)} itens · "
            f"{len(found)} candidatos com gatilho")
        candidates.extend(found)
    return candidates

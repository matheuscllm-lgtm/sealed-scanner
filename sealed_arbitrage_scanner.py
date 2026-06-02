#!/usr/bin/env python3
"""
TCG Sealed Arbitrage Scanner

Brasil (Liga Pokémon) -> EUA (TCGPlayer). Produtos selados Pokémon TCG.

Pergunta que o scanner responde:
  "Esse produto selado comprado no Brasil, por esse preço, ainda dá lucro
   se revendido nos EUA pelo preço do TCGPlayer, depois de taxas conservadoras?"

PRIMEIRA VERSÃO — mock-first
  O pipeline completo (carregar anúncios -> casar com SKU -> calcular margem
  -> classificar -> relatórios) roda sobre dados MOCKADOS. O adapter da Liga
  Pokémon (`--source liga`, em liga_adapter.py) é um esboço: o fetch via
  patchright já está pronto, mas o parsing das páginas de selado aguarda a
  investigação com probe_liga_sealed.py (a Liga responde 403 a IP de
  datacenter; o mapeamento roda local, como os probe_liga_*.py da raiz).

Uso:
  python sealed_arbitrage_scanner.py                 # roda sobre mock_data/
  python sealed_arbitrage_scanner.py --source mock
  python sealed_arbitrage_scanner.py --source liga   # NotImplementedError

Saída:
  sealed/results/<timestamp>/
    real_opportunities.csv   oportunidades GREEN
    review_required.csv      YELLOW + matches ambíguos
    rejected.csv             sem match / sem referência / margem ruim
    sealed_scan_<timestamp>.xlsx   tudo acima + premissas + summary

Princípios:
  - Nunca inventar preço. Sem referência US -> rejeitado, não estimado.
  - Cada scan é fresco: diretório novo por execução, nada de misturar runs.
  - Premissas (câmbio, taxas) sempre impressas no relatório.

Exit codes:
  0  run saudável (com ou sem oportunidades)
  1  nenhum anúncio carregado (fonte provavelmente quebrada)
  2  erro de configuração (arquivo faltando / inválido)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERRO: PyYAML não instalado. Rode: pip install -r requirements.txt")
    sys.exit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.errors import SourceBlockedError

# Idiomas não-ingleses que invalidam o match (vendemos EN no TCGPlayer).
NON_EN_LANGUAGE_TOKENS = ("japones", "japonesa", "coreano", "coreana", "chines", "chinesa")
# Padrão de numeração de carta avulsa, ex.: "238/191".
CARD_NUMBER_RE = re.compile(r"\b\d{1,3}\s*/\s*\d{1,3}\b")


# --------------------------------------------------------------------------
# Normalização
# --------------------------------------------------------------------------
def normalize(text: str) -> str:
    """minúsculas, acentos removidos, pontuação -> espaço, espaços colapsados.

    "Booster Box Surging Sparks (Inglês)" -> "booster box surging sparks ingles"
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", str(text))
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = "".join(c if c.isalnum() else " " for c in stripped.lower())
    return " ".join(cleaned.split())


def contains_term(haystack_norm: str, term: str) -> bool:
    """Match de termo por palavra inteira (evita 'tin' casar dentro de 'trainer')."""
    return f" {normalize(term)} " in f" {haystack_norm} "


# --------------------------------------------------------------------------
# Config e registry
# --------------------------------------------------------------------------
def load_yaml(path: Path, label: str) -> dict:
    if not path.exists():
        print(f"ERRO: {label} não encontrado em {path}")
        sys.exit(2)
    try:
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        print(f"ERRO: {label} inválido ({path}): {exc}")
        sys.exit(2)
    if not isinstance(data, dict):
        print(f"ERRO: {label} ({path}) não é um mapeamento YAML.")
        sys.exit(2)
    return data


# --------------------------------------------------------------------------
# Câmbio USD->BRL — fetch automático com fallback
# --------------------------------------------------------------------------
def fetch_usd_brl() -> tuple[float | None, str]:
    """Busca cotação USD->BRL em fontes públicas (sem auth, free).

    Retorna (rate, source). rate=None se todas as fontes falharem.
    Tenta AwesomeAPI (BR, bid bancário) e depois open.er-api.com (backup).
    """
    import urllib.request
    import urllib.error

    sources = [
        (
            "AwesomeAPI",
            "https://economia.awesomeapi.com.br/last/USD-BRL",
            lambda d: float(d["USDBRL"]["bid"]),
        ),
        (
            "open.er-api.com",
            "https://open.er-api.com/v6/latest/USD",
            lambda d: float(d["rates"]["BRL"]),
        ),
    ]
    for name, url, extract in sources:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "sealed-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            rate = extract(payload)
            if rate and rate > 0:
                return rate, name
        except (urllib.error.URLError, OSError, ValueError, KeyError, TypeError):
            continue
    return None, "todas as fontes falharam"


def resolve_fx_rate(config: dict) -> str:
    """Resolve cambio USD->BRL conforme config.currency.mode.

    mode=manual: usa config.currency.usd_brl direto.
    mode=fetch : tenta APIs publicas; se falhar, cai pra usd_brl manual.

    Mutates config["currency"]["usd_brl"] in-place quando fetch sucede.
    Retorna string descritiva pra log/relatorio.
    """
    currency = config.setdefault("currency", {})
    mode = (currency.get("mode") or "manual").lower()
    manual_value = currency.get("usd_brl")

    if mode != "fetch":
        return f"manual ({manual_value})"

    rate, source = fetch_usd_brl()
    if rate is None:
        print(f"  [fx] AVISO: fetch automatico falhou ({source}); usando fallback manual {manual_value}")
        return f"manual fallback ({manual_value}); fetch falhou"

    currency["usd_brl"] = rate
    return f"fetch via {source} ({rate:.4f})"


def load_json(path: Path, label: str) -> dict:
    if not path.exists():
        print(f"ERRO: {label} não encontrado em {path}")
        sys.exit(2)
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        print(f"ERRO: {label} inválido ({path}): {exc}")
        sys.exit(2)


# --------------------------------------------------------------------------
# Modelos
# --------------------------------------------------------------------------
@dataclass
class Sku:
    id: str
    name: str
    product_type: str
    set_name: str
    language: str
    set_terms: list[str]
    type_terms: list[str]
    exclude_terms: list[str]
    # Termos OBRIGATÓRIOS (todos precisam estar no título). Útil pra variantes
    # tipo Pokemon Center ETB — sem isso, ela colide com a ETB regular.
    requires_terms: list[str] = field(default_factory=list)
    # Quantidade comprada em lote para amortizar custos fixos (frete intl + 3PL).
    # Packs costumam ser comprados em ≥24 unidades; boxes/ETBs = 1.
    bulk_qty: int = 1


@dataclass
class ScanRow:
    listing_id: str
    title_br: str
    source: str
    seller: str
    url: str
    price_brl: float
    qty_avail: int | None = None      # F1.5+: estoque disponível por vendedor (None se adapter não parseou)
    sku_id: str = ""
    sku_name: str = ""
    product_type: str = ""
    set_name: str = ""
    match_confidence: str = ""        # HIGH / REVIEW / NONE
    match_candidates: list[str] = field(default_factory=list)
    us_price_usd: float | None = None
    usd_brl: float | None = None
    us_price_brl: float | None = None
    gross_profit_brl: float | None = None
    total_margin_pct: float | None = None      # (US - BR) / BR  -> filtro principal
    us_discount_pct: float | None = None        # (US - BR) / US  -> "mais barato que US"
    net_profit_brl: float | None = None
    net_margin_pct: float | None = None
    deal_confidence: str = ""         # GREEN / YELLOW / RED
    bucket: str = ""                  # real_opportunities / review_required / rejected
    main_risk: str = ""
    recommended_action: str = ""
    reject_reason: str = ""


# --------------------------------------------------------------------------
# Carregamento de anúncios (adapters)
# --------------------------------------------------------------------------
def load_listings(source: str, mock_path: Path, config: dict,
                  registry_raw: list[dict] | None = None) -> tuple[list[dict], str]:
    """Retorna (listings, descrição_da_fonte)."""
    if source == "mock":
        data = load_json(mock_path, "mock liga_listings.json")
        listings = data.get("listings", [])
        return listings, f"mock ({mock_path.name}, scanned_at={data.get('scanned_at', '?')})"

    if source == "liga":
        # Liga Pokémon via ScraperAPI (env SCRAPERAPI_KEY). Itera as
        # categorias em config.liga.categorias, baixa cada produto e
        # decodifica os preços anti-scraping via template matching.
        import liga_adapter
        listings = liga_adapter.fetch_listings(config)
        return listings, f"liga (ligapokemon.com.br via ScraperAPI, {len(listings)} listagens)"

    if source == "amazon":
        # Amazon BR: API pública acessível, busca por SKU. Sem CF, sem auth.
        import amazon_adapter
        listings = amazon_adapter.fetch_listings(config, registry_raw or [])
        return listings, f"amazon (amazon.com.br — busca ao vivo, {len(listings)} listagens)"

    if source == "olx":
        # OLX BR: __NEXT_DATA__ JSON embutido na busca, sem CF, sem auth.
        # Predomina PT-BR; o matcher filtra via exclude_terms.
        import olx_adapter
        listings = olx_adapter.fetch_listings(config, registry_raw or [])
        return listings, f"olx (olx.com.br/brasil — busca ao vivo, {len(listings)} listagens)"

    print(f"ERRO: fonte desconhecida '{source}'. Use 'mock', 'amazon', 'olx' ou 'liga'.")
    sys.exit(2)


# --------------------------------------------------------------------------
# Matcher — registry curado
# --------------------------------------------------------------------------
def build_registry(registry_data: dict) -> list[Sku]:
    skus: list[Sku] = []
    for entry in registry_data.get("skus", []):
        match = entry.get("match", {})
        skus.append(Sku(
            id=entry["id"],
            name=entry.get("name", entry["id"]),
            product_type=entry.get("product_type", ""),
            set_name=entry.get("set", ""),
            language=entry.get("language", ""),
            set_terms=match.get("set_terms", []),
            type_terms=match.get("type_terms", []),
            exclude_terms=match.get("exclude_terms", []),
            requires_terms=match.get("requires_terms", []),
            bulk_qty=int(entry.get("bulk_qty", 1)),
        ))
    if not skus:
        print("ERRO: sku_registry.yaml não tem nenhum SKU.")
        sys.exit(2)
    return skus


def match_listing(title: str, registry: list[Sku]) -> list[Sku]:
    """SKUs candidatos: set_term casa E type_term casa E todos requires_term casam E nenhum exclude_term casa."""
    norm = normalize(title)
    candidates: list[Sku] = []
    for sku in registry:
        if not any(contains_term(norm, t) for t in sku.set_terms):
            continue
        if not any(contains_term(norm, t) for t in sku.type_terms):
            continue
        if sku.requires_terms and not all(contains_term(norm, t) for t in sku.requires_terms):
            continue
        if any(contains_term(norm, t) for t in sku.exclude_terms):
            continue
        candidates.append(sku)
    return candidates


# --------------------------------------------------------------------------
# Cálculo de margem (convenção ROI: lucro sobre o capital investido)
# --------------------------------------------------------------------------
def compute_margin(price_brl: float, us_usd: float, config: dict, bulk_qty: int = 1) -> dict:
    fx = config["currency"]["usd_brl"]
    fees = config["fees"]

    us_brl = us_usd * fx
    gross_profit = us_brl - price_brl
    # Margem total do negócio: lucro sobre o capital de compra (convenção ROI).
    total_margin = gross_profit / price_brl if price_brl else 0.0
    # Quanto o BR está mais barato que a referência US (denominador = preço US).
    us_discount = gross_profit / us_brl if us_brl else 0.0

    # Taxas percentuais incidem sobre o preço de VENDA nos EUA.
    pct_fees = us_brl * (
        fees["platform_fee_pct"] + fees["payment_fee_pct"] + fees["fx_spread_pct"]
    )
    # Custos fixos (frete intl + 3PL) são amortizados por bulk_qty: você embarca
    # bulk_qty unidades no mesmo container para o 3PL. Para boxes/ETBs bulk=1
    # (já é a unidade de embarque); para packs costuma ser ≥24.
    flat_fees = (fees["international_shipping_brl"] + fees["three_pl_brl"]) / max(1, bulk_qty)
    tax = us_brl * fees.get("tax_buffer_pct", 0.0)

    net_profit = us_brl - price_brl - pct_fees - flat_fees - tax
    net_margin = net_profit / price_brl if price_brl else 0.0

    return {
        "us_price_brl": round(us_brl, 2),
        "gross_profit_brl": round(gross_profit, 2),
        "total_margin_pct": round(total_margin, 4),
        "us_discount_pct": round(us_discount, 4),
        "net_profit_brl": round(net_profit, 2),
        "net_margin_pct": round(net_margin, 4),
        "flat_fees_brl": round(flat_fees, 2),
        "bulk_qty": bulk_qty,
    }


# --------------------------------------------------------------------------
# Classificação
# --------------------------------------------------------------------------
def classify(row: ScanRow, registry: list[Sku], us_reference: dict, config: dict) -> ScanRow:
    criteria = config["deal_criteria"]
    min_total = criteria["min_total_margin_pct"]
    review_floor = criteria["review_floor_pct"]
    # ROI líquido mínimo (guarda-chuva): default 0 mantém comportamento antigo
    # pra configs legados que não tenham o campo.
    min_net = criteria.get("min_net_margin_pct", 0.0)
    min_price = config["filters"]["min_brazil_price_brl"]

    candidates = match_listing(row.title_br, registry)
    row.match_candidates = [c.id for c in candidates]

    # --- sem match -------------------------------------------------------
    if not candidates:
        row.match_confidence = "NONE"
        row.deal_confidence = "RED"
        row.bucket = "rejected"
        norm = normalize(row.title_br)
        if any(tok in norm.split() for tok in NON_EN_LANGUAGE_TOKENS):
            row.reject_reason = "idioma_nao_ingles"
            row.main_risk = "Produto não-inglês — sem liquidez no TCGPlayer"
        elif CARD_NUMBER_RE.search(row.title_br) or contains_term(norm, "carta"):
            row.reject_reason = "nao_e_selado"
            row.main_risk = "Parece carta avulsa, fora do escopo de selados"
        else:
            row.reject_reason = "sem_match_no_registry"
            row.main_risk = "Produto não está no registry curado de SKUs"
        row.recommended_action = "Ignorar (ou adicionar SKU ao registry se for selado válido)"
        return row

    # --- match ambíguo ---------------------------------------------------
    if len(candidates) > 1:
        row.match_confidence = "REVIEW"
        row.sku_name = " | ".join(c.name for c in candidates)
        row.product_type = candidates[0].product_type
        row.set_name = candidates[0].set_name
        row.deal_confidence = "YELLOW"
        row.bucket = "review_required"
        row.reject_reason = ""
        row.main_risk = (
            f"Anúncio casa com {len(candidates)} SKUs: {', '.join(row.match_candidates)}. "
            "Versão exata indefinida (ex.: ETB normal vs Pokémon Center)."
        )
        row.recommended_action = "Revisar o anúncio e identificar a versão exata antes de cotar"
        return row

    # --- match único (HIGH) ---------------------------------------------
    sku = candidates[0]
    row.match_confidence = "HIGH"
    row.sku_id = sku.id
    row.sku_name = sku.name
    row.product_type = sku.product_type
    row.set_name = sku.set_name

    if row.price_brl < min_price:
        row.deal_confidence = "RED"
        row.bucket = "rejected"
        row.reject_reason = "abaixo_do_preco_minimo"
        row.main_risk = f"Preço R$ {row.price_brl:.2f} abaixo do mínimo de operação"
        row.recommended_action = "Ignorar"
        return row

    us_usd = us_reference.get(sku.id)
    if us_usd is None:
        # Nunca inventar preço.
        row.deal_confidence = "RED"
        row.bucket = "rejected"
        row.reject_reason = "sem_referencia_us"
        row.main_risk = "Sem preço de referência no TCGPlayer para este SKU"
        row.recommended_action = "Coletar referência TCGPlayer antes de avaliar"
        return row

    fin = compute_margin(row.price_brl, us_usd, config, bulk_qty=sku.bulk_qty)
    row.us_price_usd = us_usd
    row.usd_brl = config["currency"]["usd_brl"]
    row.us_price_brl = fin["us_price_brl"]
    row.gross_profit_brl = fin["gross_profit_brl"]
    row.total_margin_pct = fin["total_margin_pct"]
    row.us_discount_pct = fin["us_discount_pct"]
    row.net_profit_brl = fin["net_profit_brl"]
    row.net_margin_pct = fin["net_margin_pct"]

    total_m = fin["total_margin_pct"]
    net_profit = fin["net_profit_brl"]
    net_m = fin["net_margin_pct"]

    # Filtro principal: margem total (lucro sobre a compra) + guarda-chuva de
    # Classificação por MARGEM BRUTA apenas (operador 2026-06-02): sem saber o
    # frete real e o tamanho do lote por remessa, a margem líquida é fabricada;
    # GREEN/YELLOW/RED é puro margem total (bruta).
    if total_m >= min_total:
        row.deal_confidence = "GREEN"
        row.bucket = "real_opportunities"
        row.main_risk = "Margem bruta — custo de frete/lote a cotar fora do scanner"
        row.recommended_action = "Validar estoque e cotar frete/lote"
    elif total_m >= review_floor:
        row.deal_confidence = "YELLOW"
        row.bucket = "review_required"
        row.main_risk = (
            f"Margem total {total_m:.1%} entre o piso {review_floor:.0%} e o alvo {min_total:.0%}"
        )
        row.recommended_action = "Revisar — margem perto do alvo"
    else:
        row.deal_confidence = "RED"
        row.bucket = "rejected"
        row.reject_reason = "margem_total_abaixo_do_minimo"
        row.main_risk = f"Margem total {total_m:.1%} abaixo do piso de {review_floor:.0%}"
        row.recommended_action = "Ignorar"
    return row


# --------------------------------------------------------------------------
# Saída — CSV
# --------------------------------------------------------------------------
CSV_COLUMNS = [
    ("listing_id", "ID Anúncio"),
    ("title_br", "Título (BR)"),
    ("source", "Fonte"),
    ("seller", "Vendedor"),
    ("url", "URL"),
    ("price_brl", "Preço BR (R$)"),
    ("qty_avail", "Qtd disponível"),
    ("sku_id", "SKU"),
    ("sku_name", "Produto (canônico)"),
    ("product_type", "Tipo"),
    ("set_name", "Coleção"),
    ("us_price_usd", "Preço US (US$)"),
    ("usd_brl", "Câmbio USD/BRL"),
    ("us_price_brl", "Preço US (R$)"),
    ("gross_profit_brl", "Lucro bruto (R$)"),
    ("total_margin_pct", "Margem total %"),
    ("us_discount_pct", "Mais barato que US %"),
    ("net_profit_brl", "Lucro líquido est. (R$)"),
    ("net_margin_pct", "Margem líquida est. %"),
    ("match_confidence", "Confiança do match"),
    ("deal_confidence", "Confiança do deal"),
    ("main_risk", "Risco principal"),
    ("recommended_action", "Ação recomendada"),
    ("reject_reason", "Motivo de rejeição"),
]


def cell_value(row: ScanRow, key: str):
    val = getattr(row, key)
    if val is None:
        return ""
    if key in ("total_margin_pct", "us_discount_pct", "net_margin_pct"):
        return f"{val * 100:.2f}"
    return val


def write_csv(rows: list[ScanRow], path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([label for _, label in CSV_COLUMNS])
        for row in rows:
            writer.writerow([cell_value(row, key) for key, _ in CSV_COLUMNS])


# --------------------------------------------------------------------------
# Saída — XLSX
# --------------------------------------------------------------------------
def compute_pool_analysis(buckets: dict, config: dict, budgets: list[float],
                           min_qty: int) -> list[dict]:
    """Pra cada SKU GREEN/YELLOW, calcula fill_pool em cada budget configurado.

    Devolve lista de dicts (1 dict por SKU). Cada dict tem:
      sku_id, sku_name, product_type, n_sellers, best_price, us_price_brl,
      results: dict[budget] -> PoolResult.
    """
    # Imports duplos pra suportar `python sealed/...` (script direto) E
    # `python -m sealed.sealed_arbitrage_scanner` / pytest (package mode).
    try:
        from sealed.lib.shipping import shipping_for_sku
        from sealed.pool_fill import fill_pool
    except ImportError:
        from lib.shipping import shipping_for_sku  # type: ignore[no-redef]
        from pool_fill import fill_pool  # type: ignore[no-redef]

    frete_cfg = config.get("frete", {}) or {}
    freight_model = frete_cfg.get("modelo", "per_seller")
    # Modelo flat final: frete = base_pct × gasto + per_seller × (n_lojas-1).
    flat_base_pct = float(frete_cfg.get("flat_base_pct", 0.05))
    flat_per_seller = float(frete_cfg.get("flat_per_seller_brl", 17.0))

    # Agrupa rows GREEN+YELLOW por sku_id; só HIGH-match (sku_id != "")
    by_sku: dict[str, list] = {}
    for bucket_key in ("real_opportunities", "review_required"):
        for r in buckets.get(bucket_key, []):
            if r.match_confidence != "HIGH" or not r.sku_id:
                continue
            by_sku.setdefault(r.sku_id, []).append(r)

    out: list[dict] = []
    for sku_id, sku_rows in by_sku.items():
        # Listings dict no formato esperado pelo pool_fill
        listings_for_pool = [
            {
                "seller": r.seller,
                "price_brl": r.price_brl,
                "qty_avail": r.qty_avail,
                "url": r.url,
            }
            for r in sku_rows
        ]
        first = sku_rows[0]
        us_brl = first.us_price_brl or 0.0
        # frete per_seller a partir do product_type (só usado se modelo=per_seller)
        frete_unit = shipping_for_sku({"product_type": first.product_type}, frete_cfg)

        results: dict[float, "PoolResult"] = {}  # type: ignore[name-defined]
        for budget in budgets:
            # Frete flat final: base_pct × gasto + per_seller × (n_lojas-1).
            results[budget] = fill_pool(
                listings_for_pool, sku_id, budget, us_brl,
                frete_unit=frete_unit,
                freight_model=freight_model,
                flat_base_pct=flat_base_pct,
                flat_per_seller_brl=flat_per_seller,
                skip_qty_unknown=True,
                min_qty_per_seller=min_qty,
            )

        prices = sorted(r.price_brl for r in sku_rows)
        out.append({
            "sku_id": sku_id,
            "sku_name": first.sku_name,
            "product_type": first.product_type,
            "n_sellers": len(sku_rows),
            "best_price": prices[0] if prices else 0.0,
            "us_price_brl": us_brl,
            "frete_unit": frete_unit,
            "freight_model": freight_model,
            "results": results,
        })

    # Sort: melhor margem realista no maior budget primeiro
    def sort_key(item):
        biggest_budget = max(budgets) if budgets else 0
        r = item["results"].get(biggest_budget)
        return -(r.recomputed_margin_vs_us if r else -999)
    out.sort(key=sort_key)
    return out


def write_xlsx(buckets: dict, config: dict, source_desc: str, path: Path,
                pool_analysis: list[dict] | None = None,
                pool_budgets: list[float] | None = None) -> bool:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("  [aviso] openpyxl não instalado — XLSX pulado (CSVs gerados normalmente).")
        return False

    wb = Workbook()
    wb.remove(wb.active)

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F4E78")
    fills = {
        "GREEN": PatternFill("solid", fgColor="C6EFCE"),
        "YELLOW": PatternFill("solid", fgColor="FFEB9C"),
        "RED": PatternFill("solid", fgColor="F2DCDB"),
    }

    def add_sheet(name: str, rows: list[ScanRow]) -> None:
        ws = wb.create_sheet(name)
        ws.append([label for _, label in CSV_COLUMNS])
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
        for row in rows:
            ws.append([cell_value(row, key) for key, _ in CSV_COLUMNS])
            fill = fills.get(row.deal_confidence)
            if fill:
                for cell in ws[ws.max_row]:
                    cell.fill = fill
        for idx, (key, label) in enumerate(CSV_COLUMNS, start=1):
            width = max(len(label) + 2, 14)
            if key in ("title_br", "sku_name", "main_risk", "recommended_action", "url"):
                width = 42
            ws.column_dimensions[get_column_letter(idx)].width = width
        ws.freeze_panes = "A2"

    add_sheet("Real Opportunities", buckets["real_opportunities"])
    add_sheet("Review Required", buckets["review_required"])
    add_sheet("Rejected", buckets["rejected"])

    # Premissas — nunca esconder.
    ws = wb.create_sheet("Assumptions")
    ws.append(["Premissa", "Valor"])
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    fees = config["fees"]
    assumptions = [
        ("Fonte dos anúncios", source_desc),
        ("Referência US", ", ".join(config["sources"]["usa"])),
        ("Câmbio USD/BRL", config["currency"]["usd_brl"]),
        ("Modo de câmbio", config["currency"]["mode"]),
        ("Taxa de marketplace (venda)", f"{fees['platform_fee_pct']:.0%}"),
        ("Taxa de pagamento", f"{fees['payment_fee_pct']:.0%}"),
        ("Spread cambial", f"{fees['fx_spread_pct']:.0%}"),
        ("Frete internacional (R$/un)", fees["international_shipping_brl"]),
        ("3PL / manuseio (R$/un)", fees["three_pl_brl"]),
        ("Buffer de imposto", f"{fees.get('tax_buffer_pct', 0.0):.0%}"),
        ("Preço mínimo BR (R$)", config["filters"]["min_brazil_price_brl"]),
        ("Margem total alvo (GREEN)", f"{config['deal_criteria']['min_total_margin_pct']:.0%}"),
        ("Piso p/ revisão (YELLOW)", f"{config['deal_criteria']['review_floor_pct']:.0%}"),
    ]
    frete_cfg = config.get("frete", {}) or {}
    if frete_cfg.get("modelo") == "flat":
        base_pct = frete_cfg.get("flat_base_pct", 0.05)
        per_seller = frete_cfg.get("flat_per_seller_brl", 17)
        assumptions += [
            ("Modelo de frete (pool)", "flat: base % + custo por loja"),
            ("Frete base (sobre gasto)", f"{base_pct:.0%}"),
            ("Frete por loja adicional (R$)", per_seller),
            ("Budget inclui frete", "sim (produtos + frete <= budget)"),
        ]
    for label, value in assumptions:
        ws.append([label, value])
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 48

    # Pool Analysis (apenas se executado com --pool-budget)
    if pool_analysis and pool_budgets:
        ws = wb.create_sheet("Pool Analysis")
        freight_model = pool_analysis[0].get("freight_model", "per_seller") if pool_analysis else "per_seller"
        # Header dinâmico — uma coluna por (métrica, budget)
        header = ["SKU", "Produto", "Tipo", "# Vendedores", "Melhor preço (R$)",
                  "US ref (R$)"]
        for b in pool_budgets:
            tag = f"R${int(b):,}".replace(",", ".")
            header.extend([
                f"Unid @ {tag}", f"Preço efetivo @ {tag}",
                f"Frete lote @ {tag}", f"Outlay @ {tag}",
                f"Margem real @ {tag} (%)", f"# Lojas @ {tag}",
            ])
        ws.append(header)
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill

        for item in pool_analysis:
            base = [
                item["sku_id"],
                item["sku_name"],
                item["product_type"],
                item["n_sellers"],
                round(item["best_price"], 2),
                round(item["us_price_brl"], 2),
            ]
            for b in pool_budgets:
                r = item["results"].get(b)
                if r and r.total_units > 0:
                    base.extend([
                        r.total_units,
                        round(r.avg_price_per_unit, 2),
                        round(r.total_freight_brl, 2),
                        round(r.total_outlay_brl, 2),
                        round(r.recomputed_margin_vs_us, 1),
                        r.n_sellers_used,
                    ])
                else:
                    base.extend(["—", "—", "—", "—", "—", "—"])
            ws.append(base)
            # Highlight: margem real do maior budget
            biggest = max(pool_budgets)
            r = item["results"].get(biggest)
            if r and r.recomputed_margin_vs_us >= 40:
                fill = fills["GREEN"]
            elif r and r.recomputed_margin_vs_us >= 30:
                fill = fills["YELLOW"]
            else:
                fill = None
            if fill:
                for cell in ws[ws.max_row]:
                    cell.fill = fill

        # Larguras
        widths = [16, 42, 18, 12, 14, 14] + [12, 18, 16, 16, 18, 12] * len(pool_budgets)
        for idx, w in enumerate(widths, start=1):
            ws.column_dimensions[get_column_letter(idx)].width = w
        ws.freeze_panes = "C2"

    # Summary
    ws = wb.create_sheet("Summary", 0)
    ws.append(["Bucket", "Qtd"])
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    for label, key in (
        ("Real Opportunities", "real_opportunities"),
        ("Review Required", "review_required"),
        ("Rejected", "rejected"),
    ):
        ws.append([label, len(buckets[key])])
    ws.append(["TOTAL", sum(len(v) for v in buckets.values())])
    # Top 5 SKUs por margem realista no maior budget
    if pool_analysis and pool_budgets:
        biggest = max(pool_budgets)
        tag = f"R${int(biggest):,}".replace(",", ".")
        ws.append([])
        ws.append([f"Top SKUs por margem realista (@ {tag})"])
        for cell in ws[ws.max_row]:
            cell.font = header_font
            cell.fill = header_fill
        ws.append(["SKU", "Unid", "Preço efetivo (R$)", "Margem real %"])
        for cell in ws[ws.max_row]:
            cell.font = Font(bold=True)
        for item in pool_analysis[:5]:
            r = item["results"].get(biggest)
            if not r or r.total_units == 0:
                continue
            ws.append([
                item["sku_name"][:40],
                r.total_units,
                round(r.avg_price_per_unit, 2),
                round(r.recomputed_margin_vs_us, 1),
            ])
    ws.column_dimensions["A"].width = 42
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 20
    ws.column_dimensions["D"].width = 14

    wb.save(path)
    return True


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------
def run(args: argparse.Namespace) -> int:
    config = load_yaml(Path(args.config), "config.yaml")
    fx_source = resolve_fx_rate(config)
    config["currency"]["_source"] = fx_source
    print(f"  [fx] cambio USD/BRL: {fx_source}")
    registry_data = load_yaml(Path(args.registry), "sku_registry.yaml")
    registry = build_registry(registry_data)

    try:
        listings, source_desc = load_listings(
            args.source, Path(args.mock), config, registry_raw=registry_data.get("skus", []),
        )
    except NotImplementedError as exc:
        print(f"ERRO: {exc}")
        return 2
    except SourceBlockedError as exc:
        # Fonte bloqueada por proteção EXTERNA (Cloudflare WAF / IP reputation).
        # O pipeline está OK; o site é que nega acesso. Condição não-fatal:
        # as outras fontes (--source amazon/liga) seguem operacionais.
        print()
        print("=" * 64)
        print(f"  FONTE BLOQUEADA (externo, não é bug do scanner)")
        print("=" * 64)
        print(f"  Fonte   : {exc.source}")
        print(f"  Motivo  : {exc.detail}")
        if exc.hint:
            print(f"  Nota    : {exc.hint}")
        print("=" * 64)
        return 0

    if not listings:
        # Fonte respondeu mas veio vazia (seletor quebrado, inventário vazio).
        # Isto É um problema real — não confundir com block externo acima.
        print("ERRO: nenhum anúncio carregado — fonte vazia ou quebrada.")
        return 1

    # Referência US (TCGPlayer via tcgcsv.com) — independente da fonte BR.
    # Rode sealed/build_us_reference.py para refrescar os preços.
    ref_data = load_json(SCRIPT_DIR / "data" / "us_reference.json", "data/us_reference.json")
    us_reference = ref_data.get("prices", {})

    rows: list[ScanRow] = []
    for item in listings:
        qty_raw = item.get("qty_avail")
        qty_avail: int | None
        try:
            qty_avail = int(qty_raw) if qty_raw is not None else None
        except (TypeError, ValueError):
            qty_avail = None
        row = ScanRow(
            listing_id=str(item.get("id", "")),
            title_br=item.get("title", ""),
            source=item.get("source", args.source),
            seller=item.get("seller", ""),
            url=item.get("url", ""),
            price_brl=float(item.get("price_brl", 0.0)),
            qty_avail=qty_avail,
        )
        rows.append(classify(row, registry, us_reference, config))

    buckets = {"real_opportunities": [], "review_required": [], "rejected": []}
    for row in rows:
        buckets[row.bucket].append(row)
    # Ordena cada balde por margem total desc — os maiores deltas saltam primeiro.
    for key in buckets:
        buckets[key].sort(
            key=lambda r: r.total_margin_pct if r.total_margin_pct is not None else -1,
            reverse=True,
        )

    # Diretório novo por run — cada scan é fresco, nada de misturar resultados.
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = SCRIPT_DIR / "results" / stamp
    out_dir.mkdir(parents=True, exist_ok=True)

    for key in buckets:
        write_csv(buckets[key], out_dir / f"{key}.csv")

    # Pool Analysis (apenas se --pool-budget passado)
    pool_budgets: list[float] = []
    pool_analysis: list[dict] | None = None
    if args.pool_budget:
        try:
            pool_budgets = [float(b.strip()) for b in args.pool_budget.split(",") if b.strip()]
        except ValueError as exc:
            print(f"  [aviso] --pool-budget inválido ({exc}); pool analysis pulada.")
            pool_budgets = []
    if pool_budgets:
        # CEP override
        if args.pool_cep:
            config.setdefault("frete", {})["destino_cep"] = args.pool_cep
        print(f"  [pool] computando análise para budgets {pool_budgets} BRL "
              f"(min_qty_per_seller={args.pool_min_qty})...")
        pool_analysis = compute_pool_analysis(buckets, config, pool_budgets, args.pool_min_qty)
        print(f"  [pool] {len(pool_analysis)} SKUs analisados")

    xlsx_path = out_dir / f"sealed_scan_{stamp}.xlsx"
    xlsx_ok = write_xlsx(buckets, config, source_desc, xlsx_path,
                          pool_analysis=pool_analysis, pool_budgets=pool_budgets)

    print()
    print("=" * 64)
    print("  TCG SEALED ARBITRAGE SCANNER")
    print("=" * 64)
    print(f"  Fonte             : {source_desc}")
    print(f"  Referência US     : {', '.join(config['sources']['usa'])}")
    print(f"  Câmbio USD/BRL    : {config['currency']['usd_brl']:.4f}  [{config['currency'].get('_source', 'manual')}]")
    print(f"  Anúncios lidos    : {len(rows)}")
    print(f"  SKUs no registry  : {len(registry)}")
    print("-" * 64)
    print(f"  Oportunidades reais (GREEN) : {len(buckets['real_opportunities'])}")
    print(f"  Revisar manualmente         : {len(buckets['review_required'])}")
    print(f"  Rejeitados                  : {len(buckets['rejected'])}")
    print("-" * 64)
    for row in buckets["real_opportunities"]:
        print(f"  GREEN  {row.listing_id}  {row.sku_name}")
        print(f"         compra R$ {row.price_brl:.2f} | margem total "
              f"{row.total_margin_pct:.1%} | {row.us_discount_pct:.1%} mais barato que US")
    for row in buckets["review_required"]:
        print(f"  YELLOW {row.listing_id}  {row.title_br}  [{row.match_confidence}]")
    # Near-misses: HIGH-match rejected, sorted by margin desc. Mostra sempre
    # que GREEN ficar abaixo de 3 — ajuda a ver o que está perto do alvo.
    if len(buckets["real_opportunities"]) < 3:
        with_margin = [r for r in buckets["rejected"] if r.total_margin_pct is not None]
        if with_margin:
            print(f"  Top {min(5, len(with_margin))} matches HIGH rejeitados (near-misses, margem desc):")
            for row in with_margin[:5]:
                tag = "RED " if row.total_margin_pct < 0 else "RED+"
                print(f"  {tag}  {row.listing_id}  {row.sku_name}")
                print(f"         compra R$ {row.price_brl:.2f} | margem total "
                      f"{row.total_margin_pct:.1%} | {row.us_discount_pct:.1%} mais barato que US")
    print("-" * 64)
    print(f"  Resultados em: {out_dir}")
    if xlsx_ok:
        print(f"  XLSX         : {xlsx_path.name}")
    print("=" * 64)
    return 0


def main() -> None:
    from lib.console import harden_stdout
    harden_stdout()  # console Windows cp1252 quebra em títulos Liga/PT-BR
    parser = argparse.ArgumentParser(description="TCG Sealed Arbitrage Scanner (Brasil -> EUA)")
    parser.add_argument("--source", default="mock", choices=["mock", "amazon", "olx", "liga"],
                        help="fonte dos anúncios (default: mock)")
    parser.add_argument("--config", default=str(SCRIPT_DIR / "config.yaml"),
                        help="caminho do config.yaml")
    parser.add_argument("--registry", default=str(SCRIPT_DIR / "sku_registry.yaml"),
                        help="caminho do sku_registry.yaml")
    parser.add_argument("--mock", default=str(SCRIPT_DIR / "mock_data" / "liga_listings.json"),
                        help="caminho do JSON de anúncios mockados")
    parser.add_argument("--pool-budget", default="",
                        help="budgets (BRL) pra análise de pool — múltiplos via vírgula. "
                             "Ex.: '5000' ou '1000,5000,10000'. Vazio = desligado (default).")
    parser.add_argument("--pool-cep", default="",
                        help="CEP destino — sobrescreve config.frete.destino_cep (calibração).")
    parser.add_argument("--pool-min-qty", type=int, default=1,
                        help="qty mínima por vendedor pra entrar no pool (default 1).")
    args = parser.parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()

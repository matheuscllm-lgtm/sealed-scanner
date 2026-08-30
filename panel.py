#!/usr/bin/env python3
"""panel.py — painel web LOCAL e SOMENTE-LEITURA da plataforma de selados.

O que é: uma "tomada" HTTP local (mesmo padrão do api.py do integrated-scanner
da frota) para EXPLORAR os deals do último scan de cada jogo no navegador —
filtros por bucket/fonte/margem/busca, agrupado por produto, com os 3 links
(oferta BR · TCG · eBay) por linha.

O que NÃO é (de propósito):
  - NÃO dispara scan (a Liga é headful/local — POST /scan é backlog declarado);
  - NÃO substitui a entrega oficial, que continua sendo a tabela markdown do
    scripts/snapshot.py colada VERBATIM no chat (regra da frota);
  - NÃO recomenda compra (ranqueia/filtra/linka; capital é do operador);
  - NÃO tem escrita nenhuma: todos os endpoints são GET sobre os arquivos que
    o run_all_sources.py já gravou.

Fonte única de leitura/agrupamento: importa collect_rows_unified /
group_products / load_run_meta / results_root_for do scripts/snapshot.py —
os números do painel são OS MESMOS da entrega, por construção.

Rodar:
    python -m uvicorn panel:app --host 127.0.0.1 --port 8078
    # abra http://127.0.0.1:8078  (ou /docs para o Swagger)
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import snapshot  # noqa: E402  (scripts/snapshot.py — fonte única de agrupamento)

GAMES = sorted(snapshot.GAME_PROFILES)
_PID_CACHE: dict[str, dict] = {}

app = FastAPI(
    title="Sealed Arbitrage — painel local (read-only)",
    description=(
        "Explora os deals do último scan de cada jogo (Pokémon / One Piece). "
        "Somente leitura; a entrega oficial é a tabela do scripts/snapshot.py. "
        "Nunca recomenda compra."
    ),
    version="1.0",
)


def _check_game(game: str) -> str:
    if game not in snapshot.GAME_PROFILES:
        raise HTTPException(status_code=422, detail=f"jogo desconhecido: {game!r}; use um de {GAMES}")
    return game


def _latest_dir(game: str) -> Path:
    d = snapshot.latest_unified_dir(snapshot.results_root_for(game))
    if d is None:
        raise HTTPException(
            status_code=404,
            detail=(f"Nenhum scan encontrado para {game!r} — rode "
                    f"`python run_all_sources.py --game {game}` primeiro."),
        )
    return d


def _rows(game: str) -> tuple[Path, list[dict]]:
    scan_dir = _latest_dir(game)
    rows = snapshot.collect_rows_unified(scan_dir)
    if not rows:
        raise HTTPException(status_code=404,
                            detail=f"{scan_dir / 'unified_deals.csv'} sem linhas válidas.")
    return scan_dir, rows


def _pid_map(game: str) -> dict:
    if game not in _PID_CACHE:
        reg = snapshot.ROOT / snapshot.GAME_PROFILES[game]["registry"]
        _PID_CACHE[game] = snapshot.load_tcg_product_ids(reg)
    return _PID_CACHE[game]


def _tcg_url(game: str, sku: str) -> str:
    pid = _pid_map(game).get((sku or "").strip())
    return f"https://www.tcgplayer.com/product/{pid}" if pid else ""


@app.get("/health")
def health():
    return {"status": "ok", "games": GAMES}


@app.get("/api/routes")
def routes():
    """Blocos `route:` (compra → venda) dos configs de cada jogo em disco."""
    out = {}
    for game, prof in snapshot.GAME_PROFILES.items():
        cfg_path = snapshot.ROOT / {"pokemon": "config.yaml",
                                    "onepiece": "config_onepiece.yaml"}[game]
        if not cfg_path.exists():
            continue
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        out[game] = cfg.get("route") or {}
    return out


@app.get("/api/status")
def status(game: str = Query("pokemon")):
    game = _check_game(game)
    scan_dir = _latest_dir(game)
    meta = snapshot.load_run_meta(scan_dir)
    rows = snapshot.collect_rows_unified(scan_dir)
    buckets = {"GREEN": 0, "YELLOW": 0, "RED": 0}
    for r in rows:
        label = {"real_opportunities": "GREEN", "review_required": "YELLOW"}.get(
            r["_bucket"], "RED")
        buckets[label] += 1
    return {
        "game": game,
        "scan_dir": scan_dir.name,
        "route_label": meta.get("route_label", ""),
        "fx": meta.get("fx"),
        "fx_source": meta.get("fx_source", ""),
        "us_ref_captured_at": meta.get("us_ref_captured_at", ""),
        "us_ref_age_days": snapshot._age_days(meta.get("us_ref_captured_at") or ""),
        "ebay_ref_captured_at": meta.get("ebay_ref_captured_at", ""),
        "ebay_ref_age_days": snapshot._age_days(meta.get("ebay_ref_captured_at") or ""),
        "ebay_stats": meta.get("ebay_stats") or {},
        "rows": len(rows),
        "buckets": buckets,
        "registry_skus": len(_pid_map(game)),
    }


@app.get("/api/deals")
def deals(game: str = Query("pokemon"),
          bucket: str | None = Query(None, description="GREEN | YELLOW | RED"),
          source: str | None = Query(None, description="Liga/OLX/Amazon/ML/mock…"),
          min_margin: float | None = Query(None, description="margem bruta mínima, em %"),
          q: str | None = Query(None, description="busca em título/produto/SKU"),
          limit: int = Query(200, ge=1, le=2000)):
    """Anúncios individuais (linhas do unified_deals.csv) com filtros."""
    game = _check_game(game)
    scan_dir, rows = _rows(game)
    label_of = {"real_opportunities": "GREEN", "review_required": "YELLOW", "rejected": "RED"}
    out = []
    for r in rows:
        lbl = label_of.get(r["_bucket"], "RED")
        if bucket and lbl != bucket.upper():
            continue
        if source and snapshot.src(r).lower() != source.lower():
            continue
        if min_margin is not None and (r["_total"] is None or r["_total"] < min_margin):
            continue
        if q:
            blob = " ".join([r.get("Título (BR)") or "", r.get("Produto (canônico)") or "",
                             r.get("SKU") or ""]).lower()
            if q.lower() not in blob:
                continue
        out.append({
            "id": r.get("ID Anúncio", ""),
            "bucket": lbl,
            "titulo": r.get("Título (BR)", ""),
            "produto": r.get("Produto (canônico)", ""),
            "tipo": r.get("Tipo", ""),
            "sku": r.get("SKU", ""),
            "fonte": snapshot.src(r),
            "vendedor": r.get("Vendedor", ""),
            "preco_brl": r.get("Preço BR (R$)", ""),
            "tcg_brl": r.get("Preço US (R$)", ""),
            "ebay_brl": r.get("eBay menor anúncio (R$)", ""),
            "margem_pct": r.get("_total"),
            "margem_ebay_pct": r.get("Margem vs eBay %", ""),
            "risco": r.get("Risco principal", ""),
            "motivo": r.get("Motivo de rejeição", ""),
            "oferta_url": r.get("URL", ""),
            "tcg_url": _tcg_url(game, r.get("SKU", "")),
            "ebay_url": r.get("eBay URL", ""),
        })
        if len(out) >= limit:
            break
    return {"game": game, "scan_dir": scan_dir.name, "count": len(out), "deals": out}


@app.get("/api/products")
def products(game: str = Query("pokemon"),
             bucket: str | None = Query(None),
             min_margin: float | None = Query(None),
             q: str | None = Query(None)):
    """Visão AGRUPADA por produto/SKU — os MESMOS grupos da entrega
    (snapshot.group_products, fonte única)."""
    game = _check_game(game)
    scan_dir, rows = _rows(game)
    label_of = {"real_opportunities": "GREEN", "review_required": "YELLOW", "rejected": "RED"}
    out = []
    for g in snapshot.group_products(rows):
        lbl = label_of.get(g["bucket"], "RED")
        if bucket and lbl != bucket.upper():
            continue
        if min_margin is not None and (g["margem"] is None or g["margem"] < min_margin):
            continue
        if q and q.lower() not in f"{g['produto']} {g['sku']}".lower():
            continue
        ref = g["ref"]
        out.append({
            "produto": g["produto"],
            "tipo": g["tipo"],
            "colecao": g["colecao"],
            "sku": g["sku"],
            "bucket": lbl,
            "br_ref": g["br_ref"],
            "tcg_brl": g["tcg_brl"],
            "ebay_brl": g["ebay_brl"],
            "margem_pct": g["margem"],
            "margem_ebay_pct": g["ebay_margem"],
            "qtd_total": g["qtd_total"],
            "qtd_partial": g["qtd_partial"],
            "n_ofertas": g["n_ofertas"],
            "suspect": g["suspect"],
            "oferta_url": (ref.get("URL") or "").strip(),
            "tcg_url": _tcg_url(game, ref.get("SKU", "")),
            "ebay_url": (ref.get("eBay URL") or "").strip(),
        })
    return {"game": game, "scan_dir": scan_dir.name, "count": len(out), "products": out}


@app.get("/api/analysis")
def analysis(game: str = Query("pokemon")):
    """Última ANÁLISE TÉCNICA (hold vs sell) do jogo — read-only, informativa.

    Lê o `results/[jogo]/analysis_*/analysis.json` mais recente (gerado por
    analyze_sealed.py). Nunca recomenda compra: rótulos são classificação
    técnica neutra; a decisão de capital é do operador."""
    import json as _json
    game = _check_game(game)
    root = snapshot.results_root_for(game)
    dirs = sorted(root.glob("analysis_*"), key=lambda d: d.stat().st_mtime,
                  reverse=True)
    for d in dirs:
        p = d / "analysis.json"
        if not p.exists():
            continue
        try:
            data = _json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        products = []
        for prod in data.get("products") or []:
            rec = prod.get("recommendation") or {}
            exp = prod.get("expected") or {}
            best_h = rec.get("best_horizon_days")
            best = (exp.get("por_horizonte") or {}).get(str(best_h)) if best_h else None
            products.append({
                "sku": prod.get("sku_id"),
                "produto": prod.get("produto"),
                "tipo": prod.get("product_type"),
                "state": rec.get("state"),
                "confidence_pct": rec.get("confidence_pct"),
                "score": (prod.get("score") or {}).get("total"),
                "compra_brl": (prod.get("buy") or {}).get("price_brl"),
                # venda_base = o preço que entrou no cálculo do lucro (projeção
                # p/ a realização quando há cenário do ciclo; senão o de hoje)
                "venda_base_usd": (prod.get("sell_now") or {}).get(
                    "gross_usd_realizacao",
                    (prod.get("sell_now") or {}).get("gross_usd")),
                "venda_hoje_usd": (prod.get("sell_now") or {}).get("gross_usd"),
                "lucro_hoje_brl": exp.get("lucro_hoje_brl"),
                "lucro_esperado_brl": (best or {}).get("lucro_esperado_brl"),
                "valor_de_esperar_brl": (best or {}).get("valor_de_esperar_brl"),
                "best_horizon_days": best_h,
                "next_review": rec.get("next_review_date"),
                "catalisador": rec.get("catalyst"),
                "risco": rec.get("risk"),
                "tendencia": ((prod.get("signals") or {}).get("price_trend") or {}).get("label"),
                "oferta": ((prod.get("signals") or {}).get("supply") or {}).get("label"),
                "reprint": ((prod.get("signals") or {}).get("reprint_risk") or {}).get("label"),
            })
        return {"game": game, "analysis_dir": d.name,
                "generated_at": data.get("generated_at"),
                "scan_dir": data.get("scan_dir"),
                "simulated": bool(data.get("simulated")),
                "cycle_days": data.get("cycle_days"),
                "net_factor": data.get("net_factor"),
                "count": len(products), "products": products}
    raise HTTPException(
        status_code=404,
        detail=(f"Nenhuma análise encontrada para {game!r} — rode "
                f"`python analyze_sealed.py --game {game}` primeiro."))


# ── página única (JS vanilla, sem build, sem CDN) ───────────────────────────
INDEX_HTML = """<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sealed Arbitrage — painel local</title>
<style>
 body{font-family:system-ui,Segoe UI,Roboto,sans-serif;margin:0;background:#0f1420;color:#e6e9f0}
 header{padding:14px 20px;background:#161d2e;display:flex;gap:14px;align-items:center;flex-wrap:wrap}
 h1{font-size:16px;margin:0 12px 0 0}
 select,input{background:#0f1420;color:#e6e9f0;border:1px solid #33405c;border-radius:6px;padding:6px 8px}
 #status{padding:8px 20px;font-size:13px;color:#9fb0d0;border-bottom:1px solid #232c42}
 table{width:100%;border-collapse:collapse;font-size:13px}
 th,td{padding:7px 9px;border-bottom:1px solid #232c42;text-align:left;vertical-align:top}
 th{position:sticky;top:0;background:#161d2e;cursor:default}
 td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
 tr:hover{background:#182136}
 .GREEN{color:#4ade80}.YELLOW{color:#facc15}.RED{color:#f87171}
 a{color:#7ab7ff;text-decoration:none}a:hover{text-decoration:underline}
 footer{padding:12px 20px;font-size:12px;color:#7787a6}
 .warn{color:#facc15}
</style></head><body>
<header>
 <h1>📦 Sealed Arbitrage — painel local <small style="color:#7787a6">(somente leitura)</small></h1>
 <label>Visão <select id="view"><option value="deals">Deals</option><option value="analysis">Análise</option></select></label>
 <label>Jogo <select id="game"><option value="pokemon">Pokémon</option><option value="onepiece">One Piece</option></select></label>
 <label>Status <select id="bucket"><option value="">todos</option><option>GREEN</option><option>YELLOW</option><option>RED</option></select></label>
 <label>Margem ≥ <input id="minm" type="number" step="5" style="width:70px" placeholder="%"></label>
 <label>Busca <input id="q" type="search" placeholder="produto / SKU"></label>
</header>
<div id="status">carregando…</div>
<div style="overflow:auto"><table id="tbl">
 <thead><tr><th>#</th><th>Status</th><th>Produto</th><th>Tipo</th>
 <th class="num">Ref. BR (R$)</th><th class="num">Ref. TCG (R$)</th><th class="num">Ref. eBay (R$)</th>
 <th class="num">Margem %</th><th class="num">vs eBay %</th><th class="num">Qtd</th><th class="num">Ofertas</th><th>⚠️</th><th>Links</th></tr></thead>
 <tbody></tbody></table></div>
<footer>Margens BRUTAS (sem taxa/frete) · Ref. eBay = menor anúncio ATIVO (pedida, não venda realizada; NUNCA classifica) ·
 painel só lê o último scan — a entrega oficial é a tabela do <code>scripts/snapshot.py</code> · sem recomendação de compra (capital é do operador).</footer>
<script>
const $=s=>document.querySelector(s);
const fmt=(v,d=2)=>v==null||v===''?'-':Number(v).toFixed(d).replace('.',',');
const esc=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const DEALS_HEAD=document.querySelector('#tbl thead').innerHTML;
const ANALYSIS_HEAD='<tr><th>#</th><th>Decisão</th><th>Produto</th><th>Tipo</th>'+
 '<th class="num">Compra (R$)</th><th class="num">Venda base (US$)</th><th class="num">Lucro hoje (R$)</th>'+
 '<th class="num">Lucro esperado (R$)</th><th class="num">Valor de esperar (R$)</th>'+
 '<th class="num">Conf.%</th><th class="num">Score</th><th>Tendência</th><th>Oferta</th><th>Reprint</th><th>Próx. revisão</th></tr>';
const ST_CLASS={JANELA_VENDA:'GREEN',EVITAR_COMPRA:'RED',DADOS_INSUFICIENTES:'YELLOW'};
async function j(u){const r=await fetch(u);if(!r.ok){throw new Error((await r.json()).detail||r.status)}return r.json()}
async function refreshAnalysis(){
 const game=$('#game').value;
 const st=await j('/api/analysis?game='+game);
 $('#tbl thead').innerHTML=ANALYSIS_HEAD;
 $('#status').innerHTML=`<b>${esc(st.analysis_dir)}</b> · scan ${esc(st.scan_dir)} · gerada ${esc(st.generated_at)} ·
  ciclo ~${esc(st.cycle_days)}d · fator líquido ×${esc(st.net_factor)}`+
  (st.simulated?' · <span class="warn">⚠️ DADOS SIMULADOS</span>':'')+
  ' · análise INFORMATIVA (rótulos neutros; decisão de capital é do operador)';
 const tb=$('#tbl tbody');tb.innerHTML='';
 st.products.forEach((p,i)=>{
  const cls=ST_CLASS[p.state]||(String(p.state||'').startsWith('MANTER')?'':'');
  tb.insertAdjacentHTML('beforeend',`<tr><td>${i+1}</td><td class="${cls}">${esc(p.state)}</td>
   <td>${esc(p.produto)}</td><td>${esc(p.tipo)}</td><td class="num">${fmt(p.compra_brl)}</td>
   <td class="num">${fmt(p.venda_base_usd)}</td><td class="num">${fmt(p.lucro_hoje_brl)}</td>
   <td class="num">${fmt(p.lucro_esperado_brl)}</td><td class="num">${fmt(p.valor_de_esperar_brl)}</td>
   <td class="num">${esc(p.confidence_pct)}</td><td class="num">${p.score==null?'-':esc(p.score)}</td>
   <td>${esc(p.tendencia)}</td><td>${esc(p.oferta)}</td><td>${esc(p.reprint)}</td>
   <td>${esc(p.next_review)}</td></tr>`)});
}
async function refresh(){
 if($('#view').value==='analysis'){
  try{await refreshAnalysis()}catch(e){$('#status').innerHTML='<span class="warn">'+esc(e.message)+'</span>';$('#tbl tbody').innerHTML=''}
  return;
 }
 $('#tbl thead').innerHTML=DEALS_HEAD;
 const game=$('#game').value,b=$('#bucket').value,m=$('#minm').value,q=$('#q').value;
 const ps=new URLSearchParams({game});if(b)ps.set('bucket',b);if(m)ps.set('min_margin',m);if(q)ps.set('q',q);
 try{
  const st=await j('/api/status?game='+game);
  const eb=st.ebay_ref_age_days==null?'<span class="warn">sem referência eBay</span>':`eBay ${st.ebay_ref_age_days}d`;
  $('#status').innerHTML=`<b>${st.scan_dir}</b> · ${st.route_label||''} · FX ${fmt(st.fx,2)} ·
   ref US ${st.us_ref_age_days==null?'?':st.us_ref_age_days+'d'} · ${eb} ·
   🟢 ${st.buckets.GREEN} 🟡 ${st.buckets.YELLOW} 🔴 ${st.buckets.RED} (${st.rows} anúncios)`;
  const data=await j('/api/products?'+ps.toString());
  const tb=$('#tbl tbody');tb.innerHTML='';
  data.products.forEach((p,i)=>{
   const links=[p.oferta_url?`<a href="${p.oferta_url}" target="_blank">oferta</a>`:'',
                p.tcg_url?`<a href="${p.tcg_url}" target="_blank">TCG</a>`:'',
                p.ebay_url?`<a href="${p.ebay_url}" target="_blank">eBay</a>`:''].filter(Boolean).join(' · ')||'—';
   tb.insertAdjacentHTML('beforeend',`<tr><td>${i+1}</td><td class="${p.bucket}">${p.bucket}</td>
    <td>${p.produto}</td><td>${p.tipo}</td><td class="num">${fmt(p.br_ref)}</td>
    <td class="num">${fmt(p.tcg_brl)}</td><td class="num">${fmt(p.ebay_brl)}</td>
    <td class="num">${fmt(p.margem_pct,1)}</td><td class="num">${fmt(p.margem_ebay_pct,1)}</td>
    <td class="num">${p.qtd_total==null?'?':p.qtd_total+(p.qtd_partial?'+?':'')}</td>
    <td class="num">${p.n_ofertas}</td><td>${p.suspect?'⚠️':''}</td><td>${links}</td></tr>`)});
 }catch(e){$('#status').innerHTML='<span class="warn">'+e.message+'</span>';$('#tbl tbody').innerHTML=''}
}
['view','game','bucket','minm','q'].forEach(id=>$('#'+id).addEventListener('input',refresh));
refresh();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML

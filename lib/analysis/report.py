"""lib/analysis/report.py — render markdown da análise (fonte ÚNICA de formato).

Consumido por: analyze_sealed.py (gera `analise_tecnica.md` + imprime),
scripts/analysis_report.py (reimprime) e scripts/snapshot.py (embute a
3ª tabela "Decisão de venda" na entrega canônica — decisão do operador,
2026-08-29: a entrega continua a mesma, ganhando a tabela de decisão).

Nunca montar tabela de análise à mão fora daqui (regra de entrega da frota).
"""
from __future__ import annotations

_STATE_EMOJI = {
    "JANELA_VENDA": "🟢", "MANTER_30D": "🔵", "MANTER_60D": "🔵",
    "MANTER_90D": "🔵", "EVITAR_COMPRA": "⛔", "DADOS_INSUFICIENTES": "⚪",
}


def _esc(text) -> str:
    return str(text or "").replace("|", "\\|")


def _brl(v) -> str:
    if v is None:
        return "-"
    return f"R$ {v:.2f}".replace(".", ",")


def _usd(v) -> str:
    return "-" if v is None else f"US$ {v:.2f}"


def _pct(v) -> str:
    return "-" if v is None else f"{v * 100:.1f}%".replace(".", ",")


def state_label(state: str) -> str:
    return f"{_STATE_EMOJI.get(state, '')} {state}".strip()


def decision_table_lines(analysis: dict) -> list[str]:
    """Tabela de DECISÃO (uma linha por produto) — a 3ª tabela da entrega."""
    lines: list[str] = []
    if analysis.get("simulated"):
        lines.append("> ⚠️ **DADOS SIMULADOS** — exemplo de demonstração, não usar para decisão.")
        lines.append("")
    lines.append(
        "| # | Decisão | Produto | Compra (R$) | Venda base (US$) | "
        "Lucro líq. hoje (R$) | Lucro esperado (R$) | Valor de esperar (R$) | "
        "Conf. % | Score | Próx. revisão |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|")
    for i, p in enumerate(analysis.get("products") or [], start=1):
        rec = p.get("recommendation") or {}
        exp = p.get("expected") or {}
        best_h = rec.get("best_horizon_days")
        best = (exp.get("por_horizonte") or {}).get(str(best_h)) if best_h else None
        sell = p.get("sell_now") or {}
        score = (p.get("score") or {}).get("total")
        lines.append(
            f"| {i} | {state_label(rec.get('state', '?'))} | "
            f"{_esc(p.get('produto'))[:55]} | {_brl((p.get('buy') or {}).get('price_brl'))} | "
            f"{_usd(sell.get('gross_usd'))} | {_brl(exp.get('lucro_hoje_brl'))} | "
            f"{_brl(best.get('lucro_esperado_brl')) if best else '-'} | "
            f"{_brl(best.get('valor_de_esperar_brl')) if best else '-'} | "
            f"{rec.get('confidence_pct', '-')} | {score if score is not None else '-'} | "
            f"{rec.get('next_review_date', '-')} |"
        )
    return lines


def _signal_line(name: str, sig: dict | None) -> str:
    if not sig:
        return f"- **{name}**: n/d"
    return f"- **{name}**: {sig.get('label', 'n/d')}"


def render_markdown(analysis: dict) -> str:
    """Relatório completo da análise (arquivo `analise_tecnica.md` + chat)."""
    lines: list[str] = []
    sim = analysis.get("simulated")
    title_extra = " (SIMULADO)" if sim else ""
    lines.append(f"# Análise técnica US — hold vs sell{title_extra} — "
                 f"{analysis.get('stamp', '?')}")
    lines.append("")
    if sim:
        lines.append("> ⚠️ **DADOS SIMULADOS** — exemplo de demonstração, "
                     "claramente rotulado; NÃO usar para decisão.")
        lines.append("")
    lines.append(
        f"**Scan analisado**: `{analysis.get('scan_dir', '?')}` · "
        f"**Câmbio**: {analysis.get('usd_brl', '?')} ({analysis.get('fx_source', '')}) · "
        f"**Ciclo operacional**: ~{analysis.get('cycle_days', '?')}d "
        "(compra → listado nos EUA) · "
        f"**Fator líquido**: ×{analysis.get('net_factor', '?')} "
        "(custos agregados — Probstein/PayPal/logística/imposto por fora)"
    )
    lines.append("")
    counts: dict = {}
    for p in analysis.get("products") or []:
        st = (p.get("recommendation") or {}).get("state", "?")
        counts[st] = counts.get(st, 0) + 1
    if counts:
        lines.append("**Decisões**: " + " · ".join(
            f"{state_label(st)} = {n}" for st, n in sorted(counts.items())))
        lines.append("")

    lines.append("## 📊 Decisão de venda por produto")
    lines.append("")
    lines.extend(decision_table_lines(analysis))
    lines.append("")

    lines.append("## 🔎 Detalhe por produto (sinais, cenários, evidências)")
    lines.append("")
    for i, p in enumerate(analysis.get("products") or [], start=1):
        rec = p.get("recommendation") or {}
        sig = p.get("signals") or {}
        sell = p.get("sell_now") or {}
        lines.append(f"### #{i} — {p.get('produto')} "
                     f"[{state_label(rec.get('state', '?'))}]")
        lines.append("")
        lines.append(_signal_line("Tendência de preço", sig.get("price_trend")))
        lines.append(_signal_line("Tendência da oferta", sig.get("supply")))
        lines.append(_signal_line("Liquidez", sig.get("liquidity")))
        lines.append(_signal_line("Risco de reprint", sig.get("reprint_risk")))
        lines.append(_signal_line("Ciclo de impressão", sig.get("print_cycle")))
        lines.append(_signal_line("Força da coleção (chases)", sig.get("set_strength")))
        lines.append("")
        lines.append(
            f"- **Vendendo agora** (base {sell.get('basis', '?')}): venda bruta "
            f"{_usd(sell.get('gross_usd'))} → receita líquida "
            f"{_brl(sell.get('receita_liquida_brl'))} → lucro líquido "
            f"{_brl(sell.get('lucro_liquido_brl'))} "
            f"(margem sobre custo {_pct(sell.get('margem_sobre_custo'))}) · "
            f"preço máx. de compra {_brl(sell.get('preco_maximo_compra_brl'))}"
        )
        scen = p.get("scenarios") or {}
        if scen:
            lines.append("")
            lines.append("| Horizonte (além do ciclo) | Pessimista | Base | Otimista |")
            lines.append("|---|---|---|---|")
            for h in sorted(scen, key=lambda x: int(x)):
                row = scen[h]
                cells = []
                for name in ("pessimista", "base", "otimista"):
                    s = row.get(name) or {}
                    cells.append(f"{_usd(s.get('price_usd'))} (p={s.get('prob', '-')})")
                lines.append(f"| {h}d | " + " | ".join(cells) + " |")
            lines.append("")
            first_h = sorted(scen, key=lambda x: int(x))[0]
            base_j = ((scen[first_h].get("base") or {}).get("justificativa") or "")
            if base_j:
                lines.append(f"  _Derivação (cenário base {first_h}d): {base_j}_")
        lines.append("")
        lines.append(f"- **Justificativa**: {rec.get('justification', '-')}")
        lines.append(f"- **Maior catalisador**: {rec.get('catalyst', '-')}")
        lines.append(f"- **Maior risco**: {rec.get('risk', '-')}")
        lines.append(f"- **Condição de invalidação**: {rec.get('invalidation', '-')}")
        lines.append(f"- **Próxima revisão**: {rec.get('next_review_date', '-')}")
        dq = p.get("data_quality") or {}
        missing = dq.get("missing") or []
        if missing:
            lines.append(f"- **Dados ausentes** (derrubam a confiança): {', '.join(missing)}")
        ev = p.get("evidence") or []
        if ev:
            lines.append("- **Evidências e fontes**:")
            for e in ev[:12]:
                url = e.get("source_url") or ""
                link = f" — [{e.get('source_type', 'fonte')}]({url})" if url.startswith("http") \
                    else f" — {e.get('source_type', '')}:{url}" if url else ""
                lines.append(f"  - {e.get('fact', '')}{link} "
                             f"({e.get('collected_at', 's/ data')})")
        lines.append("")

    lines.append("## Notas e limitações (leia antes de usar)")
    lines.append("")
    lines.append("- Classificação TÉCNICA com rótulos neutros — **a decisão de capital é do operador**; nada aqui é ordem de compra/venda.")
    lines.append("- A análise é INFORMATIVA e pós-scan: **não altera** a classificação GREEN/YELLOW/RED nem a margem bruta da entrega do scanner.")
    lines.append("- Pedida ≠ venda realizada: sold real vem SÓ das capturas Terapeak importadas (agregadas por anúncio, não por transação); anúncio ativo eBay é pedida.")
    lines.append("- `lucro_hoje` é projetado para a data de realização (~fim do ciclo de ~24d), não para o preço de agora; FX constante nos horizontes (sem previsão de câmbio).")
    lines.append("- Probabilidades/cenários derivam de comparáveis históricos reais (arquivo tcgcsv, desde 2024-02-08) + regras documentadas — nunca chute; coorte insuficiente → DADOS_INSUFICIENTES.")
    lines.append("- Ausência de dado NUNCA vira evidência favorável; SEM_EVIDENCIA de reprint ≠ risco baixo; 'esgotado' ≠ descontinuado.")
    lines.append("- Fórmulas, fontes e calibração: `ANALISE-TECNICA.md`. Previsões são logadas e conferidas contra a realidade (`scripts/evaluate_forecasts.py`).")
    lines.append("")
    lines.append(f"Gerado em {analysis.get('generated_at', '?')} via `analyze_sealed.py`")
    return "\n".join(lines) + "\n"

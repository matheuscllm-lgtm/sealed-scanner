"""Gap 2026-09-02: o teto `liga.max_products_per_category` cortava produtos
EN em silêncio. Caso real: categoria 25 (Blisters) tem 37 produtos EN, o teto
era 30 e o "Blister Unitário - Escarlate e Violeta 9 - Amigos de Jornada"
(pcode 133279, 31º da lista) nunca entrou em scan nenhum — invisível sem
nenhum aviso no log.

Duas travas:
1. `fetch_listings` avisa no log quantos produtos EN ficaram fora do teto.
2. O `config.yaml` do repo (modo local, sem custo) não pode voltar a um teto
   menor que o catálogo EN real da Liga (~40/categoria em 2026-09)."""
import pathlib

import yaml

import liga_adapter as L

CONFIG = pathlib.Path(__file__).resolve().parents[1] / "config.yaml"


def _cat_html(pcodes: list[int]) -> bytes:
    links = "".join(
        f'<a href="/?view=prod/view&amp;pcode={p}&amp;prod=(ING)%20Blister%20Unit%C3%A1rio%20-%20Set%20{p}">x</a>'
        for p in pcodes
    )
    return f"<html>{links}</html>".encode("utf-8")


class _FakeFetcher:
    def __init__(self, cat_html: bytes):
        self.cat_html = cat_html
        self.urls: list[str] = []

    def get(self, url, **kw):
        self.urls.append(url)
        if "cards/search" in url:          # URL de listagem de categoria
            return self.cat_html
        return b"<html></html>"          # página de produto vazia → 0 anúncios

    def close(self):
        pass


def test_fetch_listings_avisa_produtos_cortados_pelo_teto(monkeypatch, capsys):
    fake = _FakeFetcher(_cat_html([1, 2, 3]))
    monkeypatch.setattr(L, "_make_fetcher", lambda cfg: fake)
    L.fetch_listings({"liga": {"categorias": [25], "max_products_per_category": 2,
                               "delay_seconds": 0}})
    out = capsys.readouterr().out
    assert "acima do teto" in out
    assert "1 produto" in out                  # 3 EN − teto 2 = 1 cortado
    # 1 página de categoria + 2 páginas de produto (a 3ª ficou fora do teto)
    assert len(fake.urls) == 3


def test_fetch_listings_sem_corte_nao_avisa(monkeypatch, capsys):
    fake = _FakeFetcher(_cat_html([1, 2]))
    monkeypatch.setattr(L, "_make_fetcher", lambda cfg: fake)
    L.fetch_listings({"liga": {"categorias": [25], "max_products_per_category": 5,
                               "delay_seconds": 0}})
    assert "acima do teto" not in capsys.readouterr().out


def test_config_repo_teto_cobre_catalogo_en_da_liga():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["liga"]["max_products_per_category"] >= 100


def test_scraperapi_mode_usa_teto_proprio_e_avisa(monkeypatch, capsys):
    # Modo pago: o teto generoso do modo local NÃO pode vazar (cada produto
    # custa créditos). Sem chave própria, o scraperapi cai no default 30.
    fake = _FakeFetcher(_cat_html(list(range(1, 41))))
    monkeypatch.setattr(L, "_make_fetcher", lambda cfg: fake)
    monkeypatch.delenv("LIGA_MODE", raising=False)
    L.fetch_listings({"liga": {"categorias": [25], "mode": "scraperapi",
                               "max_products_per_category": 200, "delay_seconds": 0}})
    out = capsys.readouterr().out
    assert len(fake.urls) == 1 + 30
    assert "scraperapi" in out and "acima do teto" in out
    assert "10 produto" in out


def test_config_repo_tem_teto_scraperapi_conservador():
    cfg = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    assert cfg["liga"]["max_products_per_category_scraperapi"] <= 40

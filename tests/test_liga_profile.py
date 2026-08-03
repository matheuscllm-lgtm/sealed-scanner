"""Perfis de site da plataforma LigaMagic no `liga_adapter.py`.

Trava a parametrização por PERFIL de jogo (base_url / categorias /
categorias_nomes / set_translate / type_translate) com a garantia central:
**defaults = Pokémon byte-idêntico** (nenhum comportamento histórico muda sem
override explícito no config — os testes existentes de categorias/tradução
seguem valendo tal como estão).

E a falha honesta: `categorias: []` explícito = "IDs deste site ainda não
validados" → imprime instrução e retorna vazio, sem chutar categoria.
"""
import liga_adapter as L


# ── URLs honram o `base` do perfil ──────────────────────────────────────────
def test_category_and_product_url_default_base_unchanged():
    assert L._category_url(27) == (
        "https://www.ligapokemon.com.br/?view=cards/search&tipo=1&card=categ%3D27+searchprod%3D1"
    )
    assert L._product_url(123) == "https://www.ligapokemon.com.br/?view=prod/view&pcode=123"


def test_category_and_product_url_with_profile_base():
    op = "https://www.ligaonepiece.com.br"
    assert L._category_url(5, base=op).startswith(op + "/?view=cards/search")
    assert L._product_url(7, base=op) == f"{op}/?view=prod/view&pcode=7"


def test_parse_category_products_builds_urls_on_profile_base():
    html = '<a href="/?view=prod/view&amp;pcode=42&amp;prod=(ING)%20Booster%20Box%20OP-16">x</a>'
    op = "https://www.ligaonepiece.com.br"
    out = L.parse_category_products(html, base=op)
    assert out[0]["pcode"] == 42
    assert out[0]["url"].startswith(op + "/?view=prod/view")
    # default continua Liga Pokémon
    out_default = L.parse_category_products(html)
    assert out_default[0]["url"].startswith("https://www.ligapokemon.com.br/")


# ── tradução por perfil ─────────────────────────────────────────────────────
def test_translate_title_default_maps_unchanged():
    t = L._translate_title("(ING) Coleção Treinador Avançado - Fagulhas Impetuosas")
    assert "Elite Trainer Box" in t
    assert "Surging Sparks" in t
    assert "(English)" in t


def test_translate_title_with_profile_maps():
    t = L._translate_title(
        "(ING) Caixa de Booster - OP-16 O Tempo da Batalha",
        set_map={"O Tempo da Batalha": "The Time of Battle"},
        type_map={"Caixa de Booster": "Booster Box"},
    )
    assert "Booster Box" in t
    assert "The Time of Battle" in t
    # dicionários Pokémon NÃO são consultados quando o perfil injeta os seus
    t2 = L._translate_title("(ING) Coleção Treinador Avançado - X",
                            set_map={}, type_map={})
    assert "Elite Trainer Box" not in t2


# ── fetch_listings: perfil + falha honesta ──────────────────────────────────
class _FakeFetcher:
    def __init__(self):
        self.urls: list[str] = []

    def get(self, url, **kw):
        self.urls.append(url)
        return b"<html></html>"

    def close(self):
        pass


def test_fetch_listings_empty_categorias_is_honest_noop(monkeypatch, capsys):
    fake = _FakeFetcher()
    monkeypatch.setattr(L, "_make_fetcher", lambda cfg: fake)
    out = L.fetch_listings({"liga": {"categorias": [],
                                     "base_url": "https://www.ligaonepiece.com.br"}})
    assert out == []
    assert fake.urls == []                      # nem tentou coletar
    msg = capsys.readouterr().out
    assert "categorias está VAZIO" in msg
    assert "SETUP-VALIDACAO.md" in msg          # aponta o runbook de validação


def test_fetch_listings_uses_profile_base_and_names(monkeypatch, capsys):
    fake = _FakeFetcher()
    monkeypatch.setattr(L, "_make_fetcher", lambda cfg: fake)
    cfg = {"liga": {
        "base_url": "https://www.ligaonepiece.com.br",
        "categorias": [99],
        "categorias_nomes": {99: "Caixas de Booster OP"},
    }}
    out = L.fetch_listings(cfg)
    assert out == []                            # html vazio → 0 produtos (honesto)
    assert fake.urls and fake.urls[0].startswith("https://www.ligaonepiece.com.br/")
    assert "Caixas de Booster OP" in capsys.readouterr().out


def test_fetch_listings_absent_categorias_keeps_pokemon_defaults(monkeypatch):
    # Chave AUSENTE (config antigo) = default de sempre: todas as categorias
    # Pokémon do módulo, no domínio da Liga Pokémon.
    fake = _FakeFetcher()
    monkeypatch.setattr(L, "_make_fetcher", lambda cfg: fake)
    L.fetch_listings({"liga": {}})
    assert len(fake.urls) == len(L.DEFAULT_CATEGORIES)
    assert all(u.startswith("https://www.ligapokemon.com.br/") for u in fake.urls)

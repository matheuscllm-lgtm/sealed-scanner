"""A chave da ScraperAPI vai como query param (desenho do serviço): o endpoint
PRECISA ser https, senão a chave trafega em claro (achado do security review
2026-10-18, corrigido primeiro no ptbr-sealed-scanner)."""
import liga_adapter


def test_scraperapi_endpoint_uses_tls():
    assert liga_adapter.SCRAPERAPI_BASE.startswith("https://")

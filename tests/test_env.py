"""lib/env.py — carregador de .env compartilhado (dedup 2026-07-06).

Antes, `_load_dotenv_if_present` vivia copiado idêntico em liga_adapter,
olx_adapter e mercadolivre_adapter. Estes testes travam a semântica única:
setdefault (nunca sobrescreve env já setado), ignora comentário/linha sem `=`,
tira aspas do valor — e garantem que os 3 adapters continuam expondo o alias
módulo-local `_load_dotenv_if_present` (que os testes deles monkeypatcham).
"""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.env import load_dotenv_if_present  # noqa: E402


def test_loads_values_without_overriding_existing_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# comentário\n"
        "NOVA_CHAVE_TESTE=valor1\n"
        'CHAVE_COM_ASPAS="entre aspas"\n'
        "JA_SETADA=do_arquivo\n"
        "linha sem igual\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("NOVA_CHAVE_TESTE", raising=False)
    monkeypatch.delenv("CHAVE_COM_ASPAS", raising=False)
    monkeypatch.setenv("JA_SETADA", "do_ambiente")

    load_dotenv_if_present(env_file)

    import os
    assert os.environ["NOVA_CHAVE_TESTE"] == "valor1"
    assert os.environ["CHAVE_COM_ASPAS"] == "entre aspas"
    # setdefault: env var já setada NUNCA é sobrescrita pelo .env
    assert os.environ["JA_SETADA"] == "do_ambiente"
    # limpeza (monkeypatch não conhece as chaves criadas pelo load)
    monkeypatch.delenv("NOVA_CHAVE_TESTE", raising=False)
    monkeypatch.delenv("CHAVE_COM_ASPAS", raising=False)


def test_missing_file_is_noop(tmp_path):
    load_dotenv_if_present(tmp_path / "nao_existe.env")  # não levanta


def test_adapters_keep_module_local_alias():
    """Os testes dos adapters monkeypatcham `<adapter>._load_dotenv_if_present`;
    o dedup precisa manter o alias em cada módulo."""
    import liga_adapter
    import mercadolivre_adapter
    import olx_adapter

    for mod in (liga_adapter, olx_adapter, mercadolivre_adapter):
        assert mod._load_dotenv_if_present is load_dotenv_if_present, mod.__name__

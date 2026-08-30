"""Inteligência de mercado: parser RSS/Atom tolerante e o contrato do match
(gatilho + set do registry — manchete sem set casado é filtrada)."""
from lib.analysis import market_intel as mi

RSS = b"""<?xml version="1.0"?><rss><channel>
<item><title>Surging Sparks reprint wave announced</title>
<link>https://news/1</link><pubDate>Fri, 29 Aug 2026</pubDate></item>
<item><title>One Piece preorder opens</title><link>https://news/2</link></item>
<item><title>Surging Sparks card spotlight</title><link>https://news/3</link></item>
</channel></rss>"""


def test_parse_feed_rss():
    items = mi.parse_feed(RSS)
    assert len(items) == 3 and items[0]["link"] == "https://news/1"
    assert mi.parse_feed(b"nao e xml") == []


def test_match_exige_gatilho_E_set_do_registry():
    items = mi.parse_feed(RSS)
    feed = {"name": "n", "source_type": "news", "classification": "SINAL_DE_MERCADO"}
    out = mi.match_candidates(items, {"SSP": "Surging Sparks"}, feed, "2026-08-29")
    # item 1: gatilho + set ✔ · item 2: gatilho sem set → FORA · item 3: set sem gatilho → fora
    assert len(out) == 1
    assert out[0]["matched_set_codes"] == ["SSP"]
    assert out[0]["classification_suggested"] == "SINAL_DE_MERCADO"


def test_forum_vira_rumor_e_confirmada_e_capada():
    items = mi.parse_feed(RSS)
    out = mi.match_candidates(items, {"SSP": "Surging Sparks"},
                              {"source_type": "forum", "classification": "CONFIRMADA"},
                              "2026-08-29")
    assert out[0]["classification_suggested"] == "RUMOR"

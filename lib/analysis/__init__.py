"""lib/analysis — camada de ANÁLISE TÉCNICA US (hold vs sell) para selados.

Camada pós-scan e INFORMATIVA: consome o `unified_deals.csv` da última run +
registry + stores próprios e produz `results/[jogo]/analysis_<stamp>/`.
Nunca toca classify/compute_margin/CSV_COLUMNS nem a classificação
GREEN/YELLOW/RED do scan (não-interferência travada em teste).
"""

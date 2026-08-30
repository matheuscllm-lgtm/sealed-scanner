// terapeak_scrape.js — captura da tabela "Sold" do eBay Seller Hub Product
// Research (Terapeak) como CSV. Fornecido/validado pelo OPERADOR em 2026-08-29
// (conta real): a UI NÃO tem botão de export nem coluna de seller — este
// snippet só LÊ a tabela que a tela LOGADA já renderizou (100% oficial, nada
// de burlar autenticação; nenhum request extra é feito).
//
// COMO USAR (runbook completo em ANALISE-TECNICA.md):
//   1. Seller Hub > Research > Product research > aba "Sold"; busque o produto
//      e selecione o período (30/90 dias... — anote o período!).
//   2. ROLE a página até o fim (a tabela carrega sob demanda).
//   3. Abra o console (F12) e cole este arquivo inteiro; Enter.
//   4. O CSV cai na área de transferência — cole em
//      data/terapeak/<sku>_<AAAA-MM-DD>.csv
//   5. Importe: python scripts/import_terapeak.py data/terapeak/<arquivo>.csv \
//        --lookback-days <período usado na UI>
//      (o import busca o seller de cada item via Browse API getItem e marca
//       is_probstein; anúncio encerrado há >~90d fica sem seller — por isso
//       vale capturar MENSALMENTE.)
//
// Colunas: item_id,title,avg_sold_price,avg_shipping,total_sold,item_sales,date_last_sold,query
// Limite prático: quebre por período se passar de algumas centenas de linhas.
(() => {
  const q = document.querySelector('input[placeholder*="keywords"]')?.value || '';
  const money = s => (s.match(/-?\$?[\d,]+\.\d{2}/) || [''])[0].replace(/[$,]/g, '');
  const rows = [...document.querySelectorAll('a[href*="/itm/"]')].map(a => {
    const tr = a.closest('tr') || a.closest('[class*="row"]');
    const id = (a.href.match(/\/itm\/(\d+)/) || [])[1];
    const cells = tr ? [...tr.querySelectorAll('td')].map(td => td.innerText.trim()) : [];
    // ordem observada: Listing | Actions | Avg sold price | Avg shipping | Total sold | Item sales | Bids | Date last sold
    return [id, JSON.stringify(a.innerText.trim()), money(cells[2] || ''), money(cells[3] || ''),
            (cells[4] || '').replace(/\D/g, ''), money(cells[5] || ''), JSON.stringify(cells[7] || ''), JSON.stringify(q)];
  }).filter(r => r[0]);
  const uniq = [...new Map(rows.map(r => [r[0], r])).values()];
  const csv = ['item_id,title,avg_sold_price,avg_shipping,total_sold,item_sales,date_last_sold,query',
               ...uniq.map(r => r.join(','))].join('\n');
  copy(csv);
  console.log(`${uniq.length} anúncios copiados. Cole em data/terapeak/<sku>_<data>.csv`);
})();

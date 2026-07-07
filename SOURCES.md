# Sources ledger - Italy (IT)

See `eu-legal-mcp/PLAYBOOK.md` section 8 and `eu-legal-mcp/template/SOURCES.template.md` for the
process this file supports.

| LDH id | LDH name | Our status | Our tool(s) | Notes / rejection reason |
|---|---|---|---|---|
| IT/Normattiva | Consolidated legislation | shipped | `it_search`, `it_get_act`, `it_get_text`, `it_list_codes` | original build |
| IT/CorteCostituzionale | Constitutional Court | shipped | `it_case_search`, `it_case_get_decision`, `it_case_stats` | original build, ~22 357 decisions all eras (1956-today), native ECLI |
| IT/CassazioneCivile | Court of Cassation (civil) | shipped | `it_cassazione_search`, `it_cassazione_get` | 2026-07-07, commit 940e307. Free, keyless SentenzeWeb (`italgiure.giustizia.it/sncass`, public Solr, IODL 2.0) - a DIFFERENT service from the paid ItalgiureWeb (35M docs, subscription, correctly rejected before). ~190k civil decisions. |
| IT/CassazioneLavoro | Court of Cassation (labor) | shipped | same tools as CassazioneCivile (`szdec:L` section) | 2026-07-07, same SentenzeWeb source |
| IT/CassazioneTributaria | Court of Cassation (tax) | shipped | same tools (`szdec:5` section) | 2026-07-07, same SentenzeWeb source; ~238k combined criminal+tax+labor |
| IT/ConsiglioDiStato | Council of State | rejected | - | Open GA (CKAN) bulk export has docket metadata only, not full text. Full text lives at `portali.giustizia-amministrativa.it` behind a URL segment (`nomeFile=..._<type-code>.html`) not derivable from the bulk data - would require guessing, which risks citation hallucination. Revisit if Open GA ever adds the type code to its export. |
| IT/GazzettaUfficiale | Official Gazette | todo | - | we only have Normattiva (consolidated text), not the raw daily Gazette |
| IT/AGCM | Competition Authority | todo | - | not yet evaluated |
| IT regional legislation (20 regions) | various | todo | - | low priority vs national sources |

Last updated: 2026-07-07 (widen round, see `eu-legal-mcp/AUDIT-LOG.md`).

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
| IT/ConsiglioDiStato | Council of State | shipped | `it_ga_search`, `it_ga_get_decision` | 2026-07-08, feature-004. LDH status @ check: complete. REJECTION REVERSED (was: bulk-only view, 2026-07-07): the Open GA bulk export is still metadata-only, but the portal's OWN search (Liferay portlet at `/web/guest/dcsnprr`, plain HTTP: GET page -> p_auth token -> POST search) returns for every hit the full `nomeFile=..._NN.html` segment the bulk data lacks, a NATIVE ECLI, and the mdp full-text URL (structured GA XML). Keyless, no TDM reservation found. One backend = whole administrative jurisdiction: Consiglio di Stato 501 034, C.G.A.R.S. 53 215, all 29 TAR seats - 3 419 429 provvedimenti portal-wide (live, 2026-07-08, re-probed at ship time). Gotchas: portal year field + pagination are silent no-ops on the action URL (anno filtered client-side via the YYYYNNNNN decision id; first page only, newest first, pageSize 20/40/60); a few provvedimenti are PDF-only (flagged `document_format: pdf`, text not extracted). |
| IT/GazzettaUfficiale | Official Gazette | todo | - | we only have Normattiva (consolidated text), not the raw daily Gazette |
| IT/AGCM | Competition Authority | todo | - | not yet evaluated |
| IT regional legislation (20 regions) | various | todo | - | low priority vs national sources |
| IT/AgenziaEntrate | Revenue Agency tax doctrine (interpelli, circolari) | todo | - | LDH p1, not yet evaluated (out of budget in the 2026-07-08 round) |

Last updated: 2026-07-08 (feature-004 widen round: ConsiglioDiStato STALE-REJ re-verified and
shipped; see `eu-legal-mcp/AUDIT-LOG.md`).

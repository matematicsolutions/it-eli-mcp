# Third-party attributions

## chrisryugj/korean-law-mcp (MIT)

The `it_verify_citations` tool adapts the anti-hallucination verification pattern of
[korean-law-mcp](https://github.com/chrisryugj/korean-law-mcp) by chrisryugj, published
under the MIT License:

- the parse-verify-report loop: extract citations from free text, resolve the act name
  from the surrounding context (with a stopword strip), verify existence against the
  authoritative source;
- the range hint on a missing provision ("art. 9999 does not exist; the act has
  articles 1-372");
- the optional content check of a claimed description against the real provision text;
- the hard response semantics: `isError=true` plus a `[HALLUCINATION_DETECTED]` header
  when a cited provision does not exist, and an explicit `[NO_CITATIONS_FOUND]` marker
  (not a success) when the input contains nothing to verify.

No source code was copied. The implementation in `src/it_eli_mcp/verify.py` and
`src/it_eli_mcp/server.py` was written from scratch in Python for Italian citation
grammar (URN:NIR / Normattiva / ECLI) and for this repository's citation contract. The
content matcher uses character trigrams instead of the original's character bigrams:
bigrams fit Korean, an agglutinative script; trigrams discriminate better for
Latin-script legal Italian.

MIT License text of the original project:
https://github.com/chrisryugj/korean-law-mcp/blob/main/LICENSE

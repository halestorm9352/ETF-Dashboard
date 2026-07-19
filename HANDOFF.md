# ETF Dashboard Handoff

Last updated: 2026-07-19

## Workflow

- Claude reviews and approves each increment.
- Codex implements exactly one increment per commit.
- Run `python -m unittest discover -s tests -v` after every change.
- Do not push an increment until the user explicitly authorizes it.
- Preserve filing events as source history and present one latest,
  amendment-aware snapshot row per ETF.

## Git State

- Branch: `sync-main`
- Published `origin/main`: `40c100d4e82018c7c04c260e9447546d4d13493b`
- Increment 7 is committed locally on `sync-main` for independent review.
- `sync-main` is one commit ahead of `origin/main`.
- Do not push Increment 7 until explicitly authorized.

## Completed Increments

- Increment 1: corrected 30-minute cache semantics, added Force refresh, and
  displayed the cached fetch timestamp.
- Increment 2: deleted the obsolete scheduled launch-snapshot workflow.
- Increment 3: bounded runtime dependencies and pinned Python 3.14.
- Increment 4: capped later-filing ticker enrichment at 90 days.
- Increment 5: added per-filer partial-failure reporting while retaining
  healthy results.
- Increment 5.5: tightened ticker, placeholder-name, and theme data hygiene.
- Increment 6: gated launch candidates by filing history and distinguished
  already-effective updates and amendments.

## Increment 7

Added trimmed, accession-sourced SEC parser fixtures under
`tests/fixtures/sec/` for:

- iShares Bitcoin Trust S-1 and S-1/A.
- SEI Exchange Traded Funds N-1A multi-series index.
- Direxion Shares ETF Trust 485APOS multi-fund index.
- DBX ETF Trust 485APOS repeated ticker-proposal table.
- American Funds Insurance Series 485APOS class-only identities.
- Fidelity Concord Street Trust 485BPOS mutual-fund share classes.
- ETF Opportunities Trust 485BPOS immediate-effectiveness cover.

`tests/fixtures/sec/README.md` records each source URL, filing date, accession,
and purpose. `tests/test_sec_parser_fixtures.py` locks the current parser and
merge behavior without changing `sec_parsers.py`.

Expected failures deliberately document known gaps:

- S-1/A quoted-prose ticker `IBIT` is not extracted. Increment 9's
  post-fixture parser follow-up should address commodity-trust ticker prose.
- American Funds class-only rows lack parent-series context. Increment 8.5
  will associate classes with their parent series.
- Fidelity five-letter mutual-fund tickers are dropped. Increment 8.5 will
  capture class identifiers and tickers for vehicle classification.

Verification:

- Full suite: 36 tests passed, including 3 expected failures.
- `py_compile` passed for `tests/test_sec_parser_fixtures.py`.
- `git diff --check` passed.
- No parser regexes, readiness precedence, snapshot derivation, cache behavior,
  or production files changed.

## Increment 8.5 Notes

`<fund name>: Class X` rows are currently dropped entirely, so dual-class
mutual funds are absent until vehicle classification reintroduces them keyed
by series.

After series/class IDs exist in Increment 8, replace document-based ticker
enrichment with an exact `CIK + seriesId/classId` join against the SEC mapping
and set `enrichment_end_bound = end_bound`.

## Unrelated Files

- `README.md` remains untracked and must not be included unless explicitly
  requested.
- Ignore `.claude/worktrees/peaceful-bartik-994ff6`.
- `HANDOFF.md` is included in Increment 7 because the increment explicitly
  requires the handoff update.

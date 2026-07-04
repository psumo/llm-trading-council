# Vendored components (forks of public repos with local patches)

These three subdirectories are forks of public GitHub repos, patched locally
for this stack. Their .git history was removed to make this a single
self-contained backup repo — the CURRENT (patched) file state is what's tracked.
To re-establish upstream tracking, re-clone the origin and re-apply the diffs.

## llm-trader
- origin: https://github.com/qrak/LLM_trader
- branch: master
- HEAD at backup: a09ee3e4bcaf3bb1a7668c172a5afe3937c7abb0
- local patches (files changed vs their committed history):
  - a09ee3e Merge remote-tracking branch 'origin/master'
  - 44ff17f local: confluence-stack patches (multi-instance LLM_TRADER_HOME, 1m timeframe, Windows path sanitization, None-guards, Gemini 180s timeout)
  - 9446977 docs: add v1.0.2 changelog
  - 8674039 Merge branch 'develop' into master — v1.0.2
  - 17ccb5e feat(post_mortem): update post-mortem data structure to include llm_analysis and enhance related tests
  - 118ee97 test(blockrun): 27 orchestrator, config, and integration tests

## llm-tradebot
- origin: https://github.com/EthanAlgoX/LLM-TradeBot
- branch: main
- HEAD at backup: b443a5b23404ecfbfe1396019b4581c772ac8c65
- local patches (files changed vs their committed history):
  - b443a5b Merge pull request #6 from romanweissflog/refactoring-for-readability
  - 61ba336 fixed findings from review
  - fc1cd47 fixes after sync to upstream
  - a632f41 get rid of bad software design using type_checking - use runner factory instead of runner provider
  - d66651d some prettify changes
  - fc8c82d next refactoring: Remode symbol_manager dependency from runners and update context for a more clean signature

## orderflow
- origin: https://github.com/focus1691/orderflow.git
- branch: master
- HEAD at backup: 205ab0c5051e3532197cf569c9c963f4faa6be3b
- local patches (files changed vs their committed history):
  - 205ab0c Merge pull request #18 from 404er/master
  - b584659 Fix low field is always zero
  - 7981b12 fix low field is always zero
  - 36bd113 Update README.md
  - 2d3cf33 Update trade side
  - f4a25f4 Create LICENSE


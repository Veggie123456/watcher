# Lifecycle observation v1

Effective when worker first initializes lifecycleTracks after watcher commit d6aa64930a0d08560e217617f082a83a2fdd9647. Independent of github-portfolio-v3 bankroll and the frozen margin-exit pilot.

For currently open and future accepted paper entries, freeze the initial observed entry, reference quantity, displayed leverage and margin. Continue executable-book favorable/adverse price excursion and modeled net P&L observation after the scalp's sampled stop or one-hour exit. Preserve first observed 5/10/20 percent net receipts on both initial notional and selected margin with quote time and book hash. No source historical entry prices or backdated fills. Bootstrap coverage starts at collector activation; earlier path is explicitly unknown. Already-closed history is not silently seeded.

End at an unambiguous fresh claimed wallet+market+side CLOSED event observed with a current book, or censor at24h if source close is unknown. Identity is not independently verified. ADDED and REDUCED events are annotated with timestamps/leverage but do not change the fixed initial-exposure reference or claim proportional source fills. Ambiguous or stale events never force closes. No real orders or extra bankroll. Funding/collateral/liquidation remain incomplete, so longer observation is not proof a leveraged account survived.

Running job targets source30s, books10s with existing backoff and gaps. Track state checkpoints persist each observed maximum/minimum and milestone; compact lifecycle-quotes receipts are written at most once/minute per track; original market books remain in the shared archive. Quote gaps over20s are flagged; absent target receipts do not prove no between-tick touch. Dashboard JSON contains lifecycleTracks; website visual presentation was not changed in this run.

Seven added lifecycle tests and44 prior regression tests passed. A read-only live-book QA quoted15tracks across6markets without changing studies. Production job41209918472 at14:25:28Z persisted17tracks and119observations. Subsequent runs must verify fresh checkpoints, not assume continuous operation from code alone.

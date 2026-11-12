# Stupid Money public research collector

Separate module; does not alter or import the Tradeify scanner at repository root. No Railway, Telegram bot, wallet credentials, or live order endpoints.

## Frozen exploratory protocol: github-alert-study-v1
Effective upon this source commit, before the first collection. Not the verified Genius v0.2 study.

- Source: exact public https://www.stupidmoney.io/live?money=smart React-stream events; retain Smart and Genius source claims, including revisions. No inference of higher tiers.
- New first observations only, publication age at most 120 seconds. OPENED and ADDED tracked as separate event types. No momentum filter. Historical/revised events never become backdated entries.
- Independent $200 scenarios, $1 modeled risk, 1x, 2% stop, observed one-hour exit, max20 open. One wallet/market per24hours. No shared-portfolio or skill claims.
- Real public Hyperliquid L2 books, quantity decimals, visible depth, minimum $10 notional. Fee assumption 4.5bps/side and adverse slippage 10bps/side. Fees are modeled, funding excluded and null; no cost-complete result claim.
- Entry price is feasible observed ask/bid plus modeled slippage, not the source entry. Stops fill at the next observed executable quote, never a fabricated touch price. Gaps flagged. This does not mirror source exits.
- Raw original events, revisions, source failures, rejected entries, entry/exit books and ongoing quote observations saved as daily JSONL. Missing feed events cannot establish deletions.
- Preserve all results. No variant optimization, historic backtest, or validated edge implied. Wallet identities/tier methodology remain unverified; frozen verified Genius entries remain blocked until those gates pass.
- No Telegram account is connected. Do not upload phone numbers, sessions, API credentials or any other secrets into this public repository.

## Execution
GitHub Actions starts on the initial push and a best-effort five-minute schedule. Each job runs up to four minutes, source checks65seconds and open-position quote checks10seconds. A blocked source backs off until the next job, while existing positions continue receiving public quotes. Scheduling, setup and commit time create gaps. Jobs may be delayed/skipped;60days repository inactivity may disable schedules. Inspect Actions and state.json heartbeat; never infer activity from deployment alone.

`python -m unittest discover -s stupid-money-lab -p 'test_*.py'`

`python stupid-money-lab/watcher.py --seconds 240`

The job commits only this module's public state and data. The dashboard reads the public state without service tokens. Collection writes do not recursively trigger jobs. There is no paid provisioning or real trading.

## Entry lifecycle correction — github-entry-study-v2

Prospectively supersedes v1 on this source commit. v1 add-only starters remain auditable legacy scenarios and continue their existing exit rules; never count them as initial-entry copying or relabel them as v2.

Only a fresh first-observed **OPENED** event can start a position. An **ADDED** event requires exactly one live v2 position with the same source payload wallet, market and direction. No initial opening observed means no paper trade; retain the alert and rejection. Replay/revisions cannot duplicate a fill. Process unseen events in publication order. Initial modeled risk allowance is$0.50, with up to two matching adds of up to$0.25 each, total modeled stop risk <=$1 (0.5% of independent$200 equity). Venue quantity decimals, minimum$10, depth, fresh quotes, original stop and original one-hour deadline apply. Update weighted entry, cumulative quantity and fees on each add. These are fixed paper risk allocations, not a claim of proportional source quantities. An add after a closed/stopped position cannot reopen it. All v1 baselines and raw outcomes remain separate.

Original source leverage and recommended paper leverage1x are recorded. Default is1x. Optional repository variable `STUPID_MONEY_PAPER_LEVERAGE_MODE=source` selects source leverage on FUTURE initial entries only, validated against the current market maximum. Position quantity and dollar P&L are not multiplied; margin requirement is notional/leverage. Source account collateral, cross/isolated mechanics and liquidation are not fully modeled, so source-leverage results remain exploratory and cannot count as validated leveraged copier results. Existing positions keep their original selected leverage; new source changes do not silently change a position's margin mode.

## Shared bankroll and scalp milestones — github-portfolio-v3

Prospectively supersedes v2 for new entries upon this commit. Older independent results remain legacy, outside this bankroll. One$1,000 account; target$200 POSITION VALUE (not margin), two matching source adds up to$75 each, total position cap$350. No invented bullish/conviction score. Max20 funded positions, with actual shared available-equity/margin/cost gates;20x$200 at1x cannot fit into$1,000. Source leverage is optional and never automatically raised to force slots. Risk allowance0.5% equity initially and1% after adds. Strict OPENED-first, source-wallet/market/side matching, duplicate/staleness/minimum/depth gates, original2% stop and observed1h exit stay in force. Adds change cost basis; quantities are modeled risk allocations, not verified source proportions.

The single canonical portfolio lives in state.json. dashboard.json is a bounded recent200-position projection; daily raw JSONL and canonical state retain full records. The website no longer independently starts trades. Legacy desk tests are preserved and marked outside this account.

During each bounded270second GitHub job: public source target30seconds, concurrent executable books target10seconds, and public checkpoint commits target60seconds. Job requests remain every5minutes (GitHub minimum), can be delayed/skipped, and are NOT an always-on guarantee. Source blocks back off; no proxies or bypasses. Freshness/gaps, original events/revisions/rejections, truncated10-level books, quote references and fills are saved. Raw L2 depth insufficient within those10 levels means reject, never extrapolate. `--continuous` is available for an independently provisioned persistent host; no such host is provisioned by this update and no Railway is used.

For each funded position, retain maximum observed return and first observed+5%,+10%,+20% milestones on TWO denominators: entry notional and allocated entry margin. Mark net uses executable side/depth plus adverse10bps and assumed4.5bps/side fees; funding excluded and liquidation/source collateral incomplete. Milestone receipts preserve timestamp, book hash, actual quantity, leg count and denominator at the hit. A later add does not overwrite prior milestone basis. Only measured executable-quote observations count as confirmed hits, not profit guarantees or realized exits. Unobserved ticks are unknown. CLOSED scenarios receive independent1minute-candle audits reconstructing leg timing; wicks are possible touches, never confirmed fills. Entry/fill arithmetic, publication order, quote freshness, source identity warning, costs and gap checks are recorded per position. These deterministic checks do not imply human fact-checkers or validated wallet skill.

No historical/backdated trades or optimization from legacy outcomes. No verified tier hierarchy, wallet mapping, out-of-sample edge, US/PA live eligibility or Telegram connection is claimed. Target analysis remains exploratory and evidence-led.

## Fresh versus add-alert scalp sections — split-v4

Effective prospectively on this commit, by explicit user request. Preserve the SAME github-portfolio-v3$1,000 cash pool and any existing positions; do not reset equity or relabel legacy entries. All newly observed eligible Smart and Genius events are studied. `signalClass=fresh` requires source OPENED. For ADDED: when exactly one live matching fresh opening exists, attach a risk/cash-limited add to it; otherwise a new `signalClass=add_scalp` paper position may enter at OUR observed quote. Keep source action ADDED and original event unchanged—this is a post-add-alert scalp hypothesis, NOT a copied original opening. One open add-alert scalp per source wallet/market/side; repeat alerts do not compound it or create duplicate exposure. After closing, a genuinely new fresh add alert can start another test. Both groups share20 funded slots, shared margin/cash, modeled costs and risk limits. Sections show separate counts, P&L and5/10/20% notional/margin milestones. Old add-only studies remain legacy under their original settings.

Sizing is unchanged:$200 target position value for either entry group; only matching adds to FRESH positions can scale toward$350. No invented small-scalp advantage, bullish score, historical entry or strategy validation. Both use the existing2% observed stop/1h observed exit to avoid an unannounced exit-rule optimization.

New collector default is SOURCE leverage, matching the user's request, only if source field is numeric/readable and within current venue max. A configured recommended-mode override remains explicit. Missing/unreadable/disallowed source leverage REJECTS the matched-leverage entry and saves a reason; never silently substitutes1x. Source leverage/margin type and selected paper leverage/match status are retained. “Matched” means matching the displayed source claim, not independently verified wallet collateral. If an attached add changes the displayed source leverage, retain the initial selected setting and flag mismatch; do not silently alter existing margin mode. Funding/cross/isolated/liquidation survival remain incomplete, so leveraged milestone observations remain exploratory, not validated copier results.


## Monitoring repair effective 2026-10-31T04:20Z

Existing split-v4 sizing/exit rules and frozen Genius gates remain unchanged. New diagnostics count first-seen OPENED and ADDED events separately by Smart/Genius, retain latest200 event decisions, and expose explicit filled/retrying/skipped outcomes. All returned events are archived; old events remain in discovery but are never backdated into entries. A failed book/metadata/depth request retains the source event for retry only within its original120-second eligibility window. IDs already filled are never replayed. Full public raw evidence remains in daily JSONL; no private accounts or secrets.

The previous four-minute jobs left material gaps: BTC OPENED7266 first appeared nine minutes late. No schedule-triggered runs were visible at04:19Z despite the workflow being active. To reduce dependence on cron, the workflow now requests the next workflow_dispatch after a successful bounded collection. Normal windows run up to55minutes, push-triggered bootstrap windows2minutes, source target30s, active quote target10s and checkpoint target30s (execution/network/publication add time). Five-minute cron remains fallback; concurrency permits only one active collector. The built-in repository GITHUB_TOKEN has actions:write solely to request the same workflow; no personal token or paid host is used. Set repository variable STUPID_MONEY_MONITOR_PAUSED=true or disable workflow to stop collection and chaining. Failed tests/collection stop handoff, cron can retry. Handoffs, queue/setup time, API limits, source blocks, latest20-event truncation and failed publication still create gaps. Never guarantee every trade or exact peak capture. Telegram remains disconnected. A dispatch request alone is not proof of the next window: verify its new run and fresh public checkpoints.

Implementation tests include Smart OPENED plus Genius ADDED independent routing, attached ADDED retaining one fresh position, quote failure then recovery creating exactly one entry, and stale OPENED staying skipped. These tests validate mechanics, not profitability. Historic captured fills/losing trades are retained; no backfill or changed performance universe.

Primary scheduler references: https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow and https://github.blog/changelog/2022-09-08-github-actions-use-github_token-with-workflow_dispatch-and-repository_dispatch/ .


### Checkpoint and executable-size follow-up, 2026-10-31T04:31Z

The first repair exposed a rebase conflict during data publication. Source3ab0cf5 now uses an isolated temporary Git index and a data-only fast-forward commit atop fetched main; it never rebases the running checkout. The final evidence step calls --publish-only. An actual local bare-repository regression test preserves a concurrent unrelated source edit. Push updates now cancel/restart the old code window; normal dispatch/schedule windows remain serialized. Update interruptions remain coverage gaps and artifacts preserve the previous job's raw evidence.

Fresh Genius-claimed PUMP OPENED7277 was actually captured at04:29Z but skipped by the old sizing guard: a quantity computed from the best book level could exceed the$200 cap after deeper-level VWAP pricing. This is a sizing bug, not missing source detection. Source64bcb56 fits future initial quantities to executable multi-level depth and the unchanged notional/0.5% equity risk cap, records sizingVersion=depth-fit-v1, and retains the original displayed leverage policy. It does not raise exposure limits or backfill7277. Long/short PUMP-sized multi-level regression tests bring the suite to44 passing executions. Existing positions, outcomes, source eligibility, stops and deadlines remain unchanged. New entries use current observed quotes only; cost/funding/liquidation caveats still apply.

Verified bootstrap41168590813 completed successfully and requested workflow_dispatch41168755221, which actually started. Subsequent source upgrades interrupt that first long window; verify the latest successor/checkpoints before claiming ongoing execution. Exact gap-free coverage is still unproven.


## Immutable checkpoint publishing (2026-11-12)

`immutable-checkpoint-v1` moves in-window Git work to one background worker. At a completed cycle boundary the collector freezes matching state/dashboard generations and exact append-only raw file byte prefixes. A shared append lock includes the independent read-only oracle stream, so a captured JSONL prefix cannot end inside a row. The worker reads frozen prefixes, hashes frozen files, and updates only lab evidence paths through a separate index atop current main. No force push or running-checkout mutation is used. Non-fast-forward retries retain the same frozen bytes and preserve unrelated commits.

There is at most one in-flight generation and one latest pending generation; coalescing requires all older raw prefixes to be retained. Raw files must remain append-only. Inode/size/boundary checks reject replacement, truncation and changed captured boundaries; they do not claim to detect arbitrary adversarial in-place rewrites of earlier bytes.

`checkpoint-publications.jsonl` records observed generation, start/end, duration, success/failure and commit. `checkpoint-manifest.json` in each published checkpoint records the generation, state/dashboard hashes and raw prefix lengths. State `checkpointPublisher` distinguishes latest observed from latest published; a pending or failed operation is never called published. These diagnostic timestamps are separate from source publication, source fill, website observation and paper quote times.

Shutdown drains for five seconds, then cancels/reaps Git process groups and joins the single worker. Local full evidence remains intact for the existing final synchronous publication and artifact fallback; finalization and workflow handoff can still create gaps. In-window snapshot capture also has a small foreground cost. No claim of gap-free collection, complete source capture or improved paper performance follows from this implementation. Source parsing, eligibility, exits, sizing and study gates are unchanged.

The implementation passed 79 local unit tests including blocked-publisher paper quote updates, loss-preserving coalescing, frozen prefix boundaries, concurrent append locking, failure/retry/shutdown, real Git non-fast-forward races, unrelated-path preservation stalled subprocess cancellation, and cleanup after an actual collector CLI exception. A termination handler and finally blocks also run cleanup on SIGTERM and cycle errors. Production activation is not verified until a subsequent collector job publishes the new protocol and timing receipts.


### Publication error diagnostics (2026-11-12)

`git-command-diagnostic-v1` preserves the command stage, start/end and monotonic duration, failed/timed_out/cancelled result, return code, stderr byte counts and allowlisted error categories. Classification inspects at most 8192 stderr bytes; raw stderr, command arguments, URLs and environment are never placed in the diagnostic payload. Unknown errors remain unclassified. Categories are hints, not independently verified causes.

Publication receipts retain diagnostics from both failed attempts and also retain the first failure when a later retry succeeds. This prevents a final read-tree error from hiding an earlier timeout; it does not assert that this sequence caused any historical failure. Existing publication retry count, timeout, cancellation, frozen bytes, entry/exit/risk rules and study accounting are unchanged. The existing 79 tests plus three diagnostic/privacy/retry tests passed (82 total). Production diagnostics await the next normal collector handoff; historical stderr cannot be reconstructed.


### Retry index isolation (2026-11-12)

Deployed diagnostic receipts show write-tree timing out before a second read-tree command fails with the index_lock category. A killed command can retain its private index lock. Each retry now uses a new index pathname inside the operation's private temporary directory. It never reuses an interrupted index or deletes a working-checkout lock. Frozen blob bytes, remote parent refresh, retry count and timeouts are unchanged.

83 tests passed, including a real local Git repository regression that simulates the first interrupted write leaving a private lock, then verifies successful retry with a different index while the abandoned lock still exists, unchanged checkout index, preserved unrelated file and exact frozen state. This addresses the secondary retry lock obstruction; it does not establish or fix the original write-tree timeout cause. Production verification awaits the next normal successor.


### Write-tree child-operation diagnostics (2026-11-12)

Failed write-tree command diagnostics now include `git-trace2-summary-v1`. Each command gets its own private temporary Trace2 event file outside the evidence directory; the raw trace is removed after success or failure. Only fixed child-operation category counts and inspection/coverage fields enter public receipts. Raw arguments, URLs, session IDs, paths, configuration and environment values are not returned. Explicit configuration/environment parameter tracing is disabled.

Inspection is capped at 262144 bytes, 2048 event lines and 8192 bytes per line. Missing, empty, unreadable, malformed, unfinished or truncated traces never imply zero fetches. Observed counts are lower bounds until a valid root exit and complete untruncated parsing establish exact coverage; `exactFetchChildStarts` otherwise remains null. A positive observed fetch count can support the next hypothesis test, while zero in a partial trace cannot refute it. Raw temporary-file generation is command-time-bounded, not advertised as a hard disk-byte cap.

88 tests passed, retaining all prior 83 plus privacy/category parsing, missing/truncation/unfinished coverage, actual failed-command cleanup, successful-command result/cleanup, and an actual partial clone with a deliberately stalled upload-pack where a fetch child is observed before write-tree timeout. No `--missing-ok` option, retry/time budgets, source parser, paper entry/exit/risk or accounting policy changed. Production diagnostics require a subsequent collector to emit these fields before any root-cause claim.


## Prospective admission change — 2026-11-12
User-directed genius-top500-v1: new OPENED entries require Genius cohort and exact integer traderCard.rank 1–500 inclusive from the observed original source card. Missing, invalid or outside ranks reject with saved reasons. Broad top-1000 badges do not satisfy this rule. Save the observed rank and rule on the decision and position. Existing positions retain matching adds and exits regardless of subsequent rank/cohort changes. No retrospective entries or requalification from revisions. Maximum 100 funded open positions subject to existing $10,000 shared cash, $200 target initial notional and fixed 5x venue-cap checks; no new reset or capital injection. Percentage milestones and historical records remain intact. Source rank methodology and wallet identity remain unverified.


## Separate selected-wallet paper study — 2026-11-12
User explicitly selected https://www.stupidmoney.io/trader/0xecb63caa47c7c4e77f60f1ce858cf28dc2b82b00. `selected-wallet-paper-v1` is isolated under targetTrader with its own $10000 hypothetical cash, 100 cash-limited slots, $200 initial notional and fixed5x within venue caps. It does not alter the main Genius/top500 study. The exact selected address is required, with no Genius/rank eligibility gate in this separate study. Monitor available live website alerts and one bounded profile read per65s (403/429 backs off one hour). The current live page has a bounded Smart/Genius discovery window; profile parsing may provide no usable events. Record blocks/empty parsing honestly, not as complete coverage.
First baseline cards and pre-start publications never create copied openings; revisions do not create entries. New observed OPENED <=120s only, then matched ADDED based on readable unchanged source-margin/leverage ratios, REDUCED by declared percentage and CLOSED on observed books. Orphan adds, unknown venues, invalid quotes and insufficient cash reject. Existing source holdings at setup are excluded from copied performance. Read-only venue reconciliation can corroborate missed full closes; fills remain at discovery quotes. Preserve5/10/20% observed notional/margin first hits and peaks. Modeled4.5bps fees and10bps adverse slippage per side; funding/liquidation incomplete. No claims of complete capture, verified identity, source historical performance or independent performance when events overlap the main study. Raw evidence uses target-trader-* session JSONL. Dashboard ?view=trader uses its own ledger and profile-check status.

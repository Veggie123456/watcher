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

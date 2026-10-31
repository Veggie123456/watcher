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

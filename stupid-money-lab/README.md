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

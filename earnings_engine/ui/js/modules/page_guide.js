// =========================================================================
// page_guide — Nexus Dashboard Module
// Extracted from dashboard.js — modularization 2026-08-28
// =========================================================================
(function() {
    const API_BASE = window.API_BASE || window.location.origin;
    const app = window.app;
    if (!app) { console.error('[page_guide] window.app not initialized'); return; }
        // =========================================================================
        // 💡 COMPREHENSIVE CALCULATION LOGIC & DATA SOURCE ARCHITECTURE (19 TABS)
        // =========================================================================
        app.PAGE_GUIDES = {
            'home': {
                title: 'Market Pulse & Macro Command Center',
                icon: '🌐',
                dataSource: 'NSE indices (^NSEI, ^NSEBANK), India VIX (^INDIAVIX), FII/DII daily cash flows from NSE Bhavcopy, and cached SQLite tables.',
                what: 'Real-time macro dashboard synthesizing India VIX volatility, Fear & Greed sentiment index, market breadth, algorithmic regime predictions, and FII/DII liquidity.',
                thought: 'Macro liquidity and index volatility dictate the broad market trend. When India VIX is compressed and institutional liquidity is positive, single-stock earnings reactions experience higher continuation rates and lower downside slippage.',
                calculations: [
                    { name: 'Fear & Greed Index (0-100)', formula: '25% Volatility + 25% Momentum + 25% Market Breadth + 25% Institutional Flows', desc: '0–25 Extreme Fear, 26–45 Fear, 46–55 Neutral, 56–75 Greed, 76–100 Extreme Greed.' },
                    { name: 'Market Breadth Ratio', formula: 'Advancing Stocks / Declining Stocks across NSE All', desc: 'Values > 1.5 indicate broad-based accumulation; values < 0.70 signal market-wide distribution.' },
                    { name: 'India VIX Regime', formula: 'Live ^INDIAVIX quote vs 50-day moving average', desc: '< 15: Low Risk / Bullish Drift, 15–20: Moderate Volatility, > 20: High Hedging / Tail-Risk.' },
                    { name: 'Institutional Net Flow', formula: 'FII Net Buy/Sell + DII Net Buy/Sell (₹ Crores)', desc: 'Net capital injected or withdrawn by institutional funds during the latest market session.' }
                ],
                tips: 'Deploy maximum capital into breakout and earnings setups when Fear & Greed is between 50–75 and India VIX is < 16.'
            },
            'results': {
                title: 'Earnings Results Ledger & Post-Announcement Drift',
                icon: '📊',
                dataSource: 'Corporate filings (BSE/NSE), consensus EPS estimates, historical daily OHLCV prices, and SQLite event_dataset (13,133+ point-in-time events).',
                what: 'Displays upcoming and recent corporate earnings releases, consensus EPS estimates vs actual reported figures, 1-day historical reaction returns, surprise streaks, and quantitative beat probabilities.',
                thought: 'Post-Earnings Announcement Drift (PEAD) is one of the most robust market anomalies in empirical finance. Stocks that beat revenue and EPS expectations while expanding gross margins tend to systematically outperform benchmark indices for 1–14 trading sessions as institutional consensus models re-rate target valuations.',
                calculations: [
                    { name: '1-Day Post-Earnings Reaction', formula: '[Close(T+1) / Close(T-1)] - 1', desc: 'Measures the immediate post-announcement price reaction between the trading day before (T-1) and after (T+1) results.' },
                    { name: 'EPS Surprise %', formula: '[(Reported EPS - Estimated EPS) / |Estimated EPS|] * 100%', desc: 'Percentage magnitude by which reported earnings beat or missed consensus expectations.' },
                    { name: 'AI Up-Probability (p_up)', formula: 'LightGBM Platt-Calibrated Probability (cv=3, sigmoid)', desc: 'Machine learning model trained strictly on point-in-time data (momentum, volatility, surprise track record) predicting positive 1D reaction odds.' },
                    { name: 'Historical Beat Rate', formula: 'Positive Past Reactions / Total Tracked Releases', desc: 'Fraction of historical corporate earnings announcements resulting in positive price drift.' }
                ],
                tips: 'Look for stocks with high past beat rates (>75%) and positive 30-day pre-earnings momentum entering earnings week.'
            },
            'monthfilter': {
                title: 'Cohort Matrix & Sector Earnings Clustering',
                icon: '🗓️',
                dataSource: 'Exchange calendar disclosures mapped to market cap tiers (ticker_market_cap) and industry sectors, synchronized with present-day delta feeds.',
                what: 'Hierarchical earnings calendar grouping corporate announcements by Announcement Date → Market Cap Cohort (Large/Mid/Small) → Industry Sector, featuring present-day delta sync.',
                thought: 'Institutional capital rarely buys isolated stocks in a vacuum; it flows into entire industry cohorts. When bellwether companies (e.g. TCS, HDFC Bank) report strong numbers, sympathetic buying propagates across peer supply chains and sector ETFs. Grouping by market cap and sector isolates cohort-wide tailwinds.',
                calculations: [
                    { name: 'Market Cap Cohorts', formula: 'Mega (>₹1L Cr) · Large (₹20k-1L Cr) · Mid (₹5k-20k Cr) · Small (<₹5k Cr)', desc: 'Categorizes capitalization to calibrate position sizing, volatility expectations, and liquidity.' },
                    { name: 'Delta Sync Timestamp', formula: 'Local SQLite cache timestamp vs Live exchange corporate actions API', desc: 'Identifies newly announced, pre-poned, or rescheduled board meeting dates within 24 hours.' },
                    { name: 'Sector Density', formula: 'Count of sector peer companies reporting in the same ±3 day window', desc: 'Higher density clusters increase sector correlation and sympathy move potential.' }
                ],
                tips: 'Trade the highest-quality peer in a sector cohort once the leading bellwether confirms a strong quarterly beat.'
            },
            'scanner': {
                title: 'Multi-Category Fundamental & Technical Scanner',
                icon: '🔍',
                dataSource: 'Daily NSE OHLCV bars, calculated 52-week price statistics (ticker_metrics), volume deques, and classified regulatory filings.',
                what: 'Curated scanner filtering companies into high-momentum institutional themes: 52-Week High Breakouts, Deliverable Volume Surges, Corporate Order Wins, Margin Expansions, and Share Buybacks.',
                thought: 'Alpha generation requires continuous pre-filtering across distinct market catalysts. Scanning pre-classified catalysts eliminates manual noise and highlights equities experiencing abnormal institutional accumulation before earnings.',
                calculations: [
                    { name: '52W High Proximity', formula: '[Current Price / 52W High] - 1', desc: 'Triggers when price is trading within 3.0% of its annual ceiling, indicating momentum continuation.' },
                    { name: 'Volume Surge Ratio', formula: '5-Day Average Volume / 63-Day Baseline Volume', desc: 'Surge flagged when ratio ≥ 2.0x, denoting institutional accumulation rather than retail churn.' },
                    { name: 'Order Win Score', formula: 'Contract Value / TTM Annual Revenue (0-100% impact)', desc: 'Scores corporate contract wins by materiality relative to existing annual top-line revenue.' }
                ],
                tips: 'Filter for Volume Surges accompanied by Order Wins for the highest conviction trend-continuation setups.'
            },
            'catalysts': {
                title: 'Corporate Catalysts & AI Impact Scoring',
                icon: '⚡',
                dataSource: 'BSE/NSE corporate regulatory filings, exchange disclosures, press announcements, and LLM text extraction engine.',
                what: 'Real-time regulatory filings feed, strategic corporate actions, management commentary, and AI-scored sentiment impact ratings (0–100%).',
                thought: 'Markets are information processing machines. Traditional news feeds inundate traders with un-actionable headlines. Categorizing material corporate events (FDA approvals, major contracts, acquisitions, buybacks) and scoring their directional impact separates high-conviction catalysts from general market chatter.',
                calculations: [
                    { name: 'AI Impact Score (0-100%)', formula: 'LLM Multi-Prompt Evaluation on Future Free Cash Flow', desc: 'Scores the fundamental business impact: >80% Major Catalyst, 50-80% Moderate, <50% Minor.' },
                    { name: 'Sentiment Polarity', formula: 'Directional Classification (Bullish / Neutral / Bearish)', desc: 'Evaluates whether announcement enhances earnings visibility or increases risk.' },
                    { name: 'Impact Horizon', formula: 'Short Term (1-3D) · Medium Term (1-2W) · Long Term (1-2Q)', desc: 'Expected temporal duration of institutional re-positioning following disclosure.' }
                ],
                tips: 'Focus on high impact (>80%) catalysts on mid-cap equities where news is often slower to be fully priced in.'
            },
            'gainers': {
                title: 'Daily Gainers & Deliverable Volume Spikes',
                icon: '🚀',
                dataSource: 'NSE Bhavcopy daily delivery trade reports (data/prices.py) and historical daily OHLCV series.',
                what: 'Tracks top daily percentage advancers, deliverable volume spikes (>2.0x 20-day average), and tight multi-session consolidation coils.',
                thought: 'Deliverable volume (shares taken into demat custody rather than squared off intraday) is the clearest signature of institutional smart money accumulation. A price move on 3x average deliverable volume signals long-term positioning rather than transient retail day trading.',
                calculations: [
                    { name: 'Deliverable Volume Spike', formula: 'Today Delivery Volume / 20-Day Mean Delivery Volume', desc: 'Spike is flagged when ratio ≥ 2.0x, isolating genuine institutional accumulation.' },
                    { name: 'Consolidation Width %', formula: '[(20-Day High - 20-Day Low) / 20-Day Low] * 100%', desc: 'Values < 8.0% denote a tight volatility squeeze/base ready for explosive expansion.' },
                    { name: '7D & 30D Momentum', formula: '[(Close_today - Close_k_days_ago) / Close_k_days_ago] * 100%', desc: 'Trailing momentum returns over 7 and 30 trading session horizons.' }
                ],
                tips: 'A delivery surge emerging from a multi-week tight base provides ideal low-risk breakout entries.'
            },
            'breakout': {
                title: 'Breakout Radar & Historical Outcome Engine',
                icon: '⚡',
                dataSource: 'Point-in-time OHLCV series, 14-day Average True Range (ATR), SQLite breakout_radar audit tables, and historical backtest date picker.',
                what: 'Multi-factor 0–100 breakout scoring engine and point-in-time historical backtest date picker. Evaluates Resistance Proximity (30 pts), Volume Surge (20 pts), Volatility Compression (15 pts), Momentum (15 pts), and Fundamentals (20 pts), verifying predicted vs realized outcomes.',
                thought: 'Volatility cycles strictly alternate between compression (coiling) and expansion (breakout). Identifying equities with narrow ATR volatility squeezes right below major resistance that also possess volume accumulation and earnings quality yields asymmetric risk/reward setups with minimal drawdown.',
                calculations: [
                    { name: 'Composite Breakout Score (0-100)', formula: '30% Resistance + 20% Volume + 15% Squeeze + 15% Momentum + 20% Quality', desc: 'Scores ≥ 75 indicate high-conviction breakout setups.' },
                    { name: 'Breakout Trigger Price', formula: 'max(20-Day High, 52-Week High)', desc: 'The exact structural resistance ceiling that price must cross to confirm breakout.' },
                    { name: 'Target & Stop Loss', formula: 'Target = Trigger + max(8%, 2x ATR) · SL = Signal - min(5%, 1.5x ATR)', desc: 'Dynamically adjusted target and invalidation stop calibrated to volatility.' },
                    { name: 'Historical Outcome Audit', formula: 'Realized Return vs Target & Stop Loss over 14 sessions', desc: 'Target Hit 🎯 (Reached target), Succeeded ✅ (>+4%), Retraced ⚠️, Stop Loss 🛑 (Hit SL).' }
                ],
                tips: 'Use the Date Picker to test setups from 30 or 60 days ago to observe how high-score candidates performed.'
            },
            'institutional': {
                title: 'Institutional Flows & Smart Money Directory',
                icon: '🏛️',
                dataSource: 'NSE quarterly shareholding disclosures (promoters, FIIs, DIIs/MFs, HNIs), bulk/block deal transaction records, and institutional_activity DB tables.',
                what: '50-50 split radar tracking equities under aggressive mutual fund / FII accumulation, trailing shareholding breakdown with QoQ deltas, block deals, and full investor portfolio drilldowns.',
                thought: 'Institutional investors (Mutual Funds, FIIs, Whales) control over 75% of market liquidity. Tracking where smart money is expanding or liquidating stakes reveals long-term multi-quarter positioning ahead of retail participants.',
                calculations: [
                    { name: 'Accumulation Score (0-100)', formula: '40% Net Fund Flow + 30% Institutional Stake % + 20% Volume + 10% Momentum', desc: 'Scores ≥ 70 denote aggressive institutional buying.' },
                    { name: 'Net Tracked Flow (₹ Cr)', formula: 'Estimated Inflow - Estimated Outflow across Tracked Funds', desc: 'Net rupee value accumulated or distributed over the most recent filing cycle.' },
                    { name: 'QoQ Shareholding Delta', formula: 'Filing_Stake%(Q_t) - Filing_Stake%(Q_{t-1})', desc: 'Quarter-over-Quarter stake change in basis points for FII and DII/Mutual Funds.' },
                    { name: 'Institutional Stake %', formula: 'FII % + DII % + Super Investor % from latest filing', desc: 'Total percentage of equity float locked up in institutional portfolios.' }
                ],
                tips: 'Look for equities where both FII and Mutual Fund stakes increased concurrently (QoQ deltas > +0.50%).'
            },
            'repeaters': {
                title: 'Quarter Repeaters & AI Forward Earnings Radar',
                icon: '🔁',
                dataSource: 'Historical quarterly earnings surprises, post-earnings week-high peak returns, active industry themes, and consensus ML models.',
                what: 'Screens companies delivering consistent earnings beats (EPS surprise > 0%) and post-earnings week-high rallies, enriched with QoQ beat streaks, active industry buzz themes, and forward AI forecasts.',
                thought: 'Companies that beat earnings and rally post-results demonstrate institutional buying and pricing power. Combining prior quarter delivery, material news flow (order wins/capex), and industry themes allows Multi-Model AI to accurately predict upcoming quarter repeat beats.',
                calculations: [
                    { name: 'Prior EPS Surprise %', formula: '[(Reported EPS - Estimated EPS) / |Estimated EPS|] * 100%', desc: 'Beat percentage achieved in the immediately preceding quarter.' },
                    { name: 'Week Peak Rally %', formula: '[max(High_{T+1...T+5}) - Close(T-1)] / Close(T-1) * 100%', desc: 'Maximum percentage price surge during the 5 trading sessions following results.' },
                    { name: 'QoQ Beat Streak', formula: 'Consecutive quarters with positive EPS Surprise', desc: '1Q, 2Q, 3Q+ streak reflecting persistent fundamental operational momentum.' },
                    { name: 'AI Repeat Probability', formula: 'Ensemble ML Classifier (Surprise Track + Momentum + Catalysts)', desc: 'Probability (0-100%) that the stock will beat expectations again in the upcoming release.' }
                ],
                tips: 'Focus on 3Q+ beat streak companies with high industry buzz tailwinds (e.g. EMS, Defense, Power Infra).'
            },
            'new-additions': {
                title: 'Recent Market Additions & IPOs Tracker',
                icon: '🆕',
                dataSource: 'NSE official new listings Bhavcopy feed, exchange debut announcements, and historical price ingestion table (price_history).',
                what: 'Tracks newly listed companies, recent IPOs, direct listings, and debut quarterly earnings dates on the National Stock Exchange (NSE).',
                thought: 'Newly listed equities experience significant price discovery and institutional accumulation cycles. Tracking them early allows quantitative traders to spot post-IPO base breakouts before mainstream analyst coverage begins.',
                calculations: [
                    { name: 'Listing Age (Days)', formula: 'Current Date - Official NSE Listing Date', desc: 'Number of calendar days elapsed since the stock debuted on the exchange.' },
                    { name: 'Series Classification', formula: 'EQ (Normal Equity) · BE (Book Entry / Trade-for-Trade) · SM (SME)', desc: 'Trading series category dictating circuit filter and settlement rules.' },
                    { name: 'Debut Earnings Proximity', formula: 'Scheduled First Results Date - Today', desc: 'Identifies impending inaugural quarterly financial disclosures.' }
                ],
                tips: 'Look for recent IPOs forming tight 3–6 week consolidation bases with deliverable volume accumulation.'
            },
            'swing': {
                title: 'Swing Range Channels & Cyclic Oscillations',
                icon: '〰️',
                dataSource: 'Historical daily OHLCV pivot points, automated swing range detection engine (data/swing_ranges.py), and SQLite swing_ranges table.',
                what: 'Automated horizontal channel detection identifying established support and resistance boundaries, cycle counts, oscillation durations, and actionable channel trading zones.',
                thought: 'Equities spend over 70% of market sessions oscillating within horizontal channels defined by institutional liquidity pools. Buying at validated support and taking profit at channel resistance offers high win-rate cyclical trades with tight invalidation levels.',
                calculations: [
                    { name: 'Channel Floor (Support)', formula: 'Cluster of ≥ 3 swing lows within 1.5% price tolerance band', desc: 'Established demand floor where buyers systematically step in.' },
                    { name: 'Channel Ceiling (Resistance)', formula: 'Cluster of ≥ 3 swing highs within 1.5% price tolerance band', desc: 'Established supply ceiling where profit taking occurs.' },
                    { name: 'Buy Zone Threshold', formula: 'Channel Floor + 0.20 * (Channel Ceiling - Channel Floor)', desc: 'Lower 20% of channel width offering optimal risk/reward entry.' },
                    { name: 'Cycle Duration', formula: 'Average trading days to traverse from floor to ceiling', desc: 'Expected holding horizon per completed swing cycle.' }
                ],
                tips: 'Set stop losses 1.5% below channel support and aim for the upper 25% zone of the channel.'
            },
            'kronos': {
                title: 'Kronos AI 14-Day Neural Sequence Forecast',
                icon: '🔮',
                dataSource: 'Kronos Deep Autoregressive Sequence Neural Network (PyTorch / GPU cuda:0) trained on multi-scale price, volume, and volatility series.',
                what: 'Deep sequence neural network forecasting 14-day price paths, dynamic confidence bands, support/resistance channel projections, and realization audit logs.',
                thought: 'Financial time-series exhibit complex non-linear autoregressive structures. Kronos AI captures multi-scale temporal dependencies across price action and volatility to project likely forward trajectories and turning points post-earnings.',
                calculations: [
                    { name: 'Projected 14D Path', formula: 'Sequential Neural Price Trajectory [t+1 ... t+14]', desc: 'Daily forward projected closing prices over a 14 trading day horizon.' },
                    { name: 'Support & Resistance Projections', formula: 'Trajectory Envelope Minima & Maxima with Volatility Bands', desc: 'Algorithmic turning points and target zones calculated along the projected path.' },
                    { name: 'Realization Error (RMSE)', formula: 'sqrt( (1/N) * sum( (Actual_t - Predicted_t)^2 ) )', desc: 'Audited historical accuracy tracking prediction divergence against realized prints.' }
                ],
                tips: 'Combine Kronos trajectory direction with multi-model AI consensus for maximum directional confidence.'
            },
            'consensus': {
                title: 'Multi-Model AI Consensus Engine',
                icon: '🤖',
                dataSource: 'OpenRouter parallel LLM inference across DeepSeek-R1, Llama-3.3-70B, Qwen-2.5-72B, and Mistral-Large, plus local Ollama host.',
                what: 'Ensemble reasoning across DeepSeek-R1 (logical chain-of-thought), Llama-3.3-70B (macro/quant), Qwen-2.5-72B (patterns), and Mistral/Gemini (news catalysts), generating unified verdicts and target ranges.',
                thought: 'Single LLM models suffer from idiosyncratic hallucinations and blind spots. Orchestrating distinct specialized open-weight models in parallel—each evaluating from different analytical perspectives—produces robust ensemble signals superior to any single model.',
                calculations: [
                    { name: 'Consensus Agreement Strength', formula: 'Sum(Confidence of Majority Models) / Sum(Total Confidence) * 100%', desc: 'Agreement magnitude (0–100%) across polled AI reasoning engines.' },
                    { name: 'Synthesized Target Price', formula: 'Confidence-Weighted Median of Individual Model Targets', desc: 'Consensus price target calibrated against structural resistance levels.' },
                    { name: 'Recommended Stop Loss', formula: 'Confidence-Weighted Invalidation Floor below Structural Support', desc: 'Strict trade invalidation price recommended by consensus.' },
                    { name: 'Risk / Reward Ratio', formula: '(Target Price - Current Price) / (Current Price - Stop Loss)', desc: 'Calculated payout ratio; only setups with R:R ≥ 2.0x are recommended.' }
                ],
                tips: 'Trigger single-model runs via the matrix buttons if you wish to refresh one specific model without consuming global API quotas.'
            },
            'buydip': {
                title: 'Buy The Dip — Mean Reversion on Quality Equities',
                icon: '📉',
                dataSource: 'Daily price history, 14-day Relative Strength Index (RSI), 200-day Simple Moving Average (SMA), and multi-quarter fundamental beat scores.',
                what: 'Identifies high-quality compounders with pristine multi-quarter earnings track records currently experiencing temporary oversold pullbacks (RSI < 35, near 200 SMA).',
                thought: 'Market overreactions and short-term liquidity shocks frequently push structurally growing, profitable businesses into deep oversold territory. Buying quality compounders at support yields high asymmetric reward with minimal long-term downside.',
                calculations: [
                    { name: 'Quality Score (1-9)', formula: '3 pts (Beat Rate ≥ 75%) + 3 pts (Margin Expansion) + 3 pts (Low Debt)', desc: 'Fundamental quality filter ensuring only high-earning businesses qualify.' },
                    { name: 'RSI(14)', formula: '100 - [100 / (1 + AvgGain_14 / AvgLoss_14)]', desc: 'Values < 35 denote oversold conditions ripe for mean reversion.' },
                    { name: 'Distance to 200 SMA', formula: '[(Current Price - 200D SMA) / 200D SMA] * 100%', desc: 'Measures proximity to the institutional long-term trend baseline (ideal within ±4%).' }
                ],
                tips: 'Only buy dips on stocks with Quality Scores ≥ 7 and intact long-term fundamental earnings growth.'
            },
            'backtest': {
                title: 'Walk-Forward Quantitative Backtesting Engine',
                icon: '🔬',
                dataSource: 'SQLite event_dataset spanning 2015–2026, walk-forward engine (backtest/engine.py), and simulated execution models.',
                what: 'Quarterly walk-forward simulation of LightGBM predictions, calculating Sharpe Ratio, Sortino Ratio, Maximum Drawdown, Win Rate, and transaction cost modeling.',
                thought: 'Standard in-sample backtests overfit to past noise. Walk-forward quarterly retraining trains exclusively on past data (T-1) and evaluates strictly out-of-sample on future quarters, providing rigorous statistical proof of edge.',
                calculations: [
                    { name: 'Walk-Forward Out-of-Sample Return', formula: 'Side * [Close(T+1) / Close(T-1) - 1] - 0.0010 Cost', desc: 'Simulates long (p ≥ 0.50) or short (p ≤ 0.50) trade net of 10 bps slippage/brokerage.' },
                    { name: 'Sharpe Ratio per Event', formula: 'Mean(Net Return) / StdDev(Net Return) * sqrt(252)', desc: 'Excess annualized return per unit of realized volatility.' },
                    { name: 'Maximum Drawdown (MDD)', formula: 'max_t [ (Peak_Equity - Equity_t) / Peak_Equity ] * 100%', desc: 'Deepest peak-to-trough equity decline across the backtest horizon.' },
                    { name: 'Profit Factor', formula: 'Gross Realized Profits / Gross Realized Losses', desc: 'Total winning trade gains divided by total losing trade losses.' }
                ],
                tips: 'Maintain transaction cost modeling (10 bps slippage/commission) to reflect realistic live execution performance.'
            },
            'watchlist': {
                title: 'Custom Watchlist Hub & Portfolio Streaming',
                icon: '⭐',
                dataSource: 'SQLite watchlists table replicated to Turso Cloud DB, live OHLCV price streams, and swing range overlays.',
                what: 'Manage custom watchlists, view live price quotes, track deliverable volume, and synchronize portfolios seamlessly with Turso Cloud database.',
                thought: 'Efficient portfolio management requires personalized grouping of monitored equities, rapid switching between universes, and instantaneous access to deep-dive analytics.',
                calculations: [
                    { name: 'Real-time Net P&L %', formula: '[(Current Live Price - Cost Basis) / Cost Basis] * 100%', desc: 'Position return tracked live against demat entry cost basis.' },
                    { name: 'Cloud Sync Verification', formula: 'Dual SQLite local + Turso Cloud HMAC verification', desc: 'Guarantees watchlists and custom swing ranges persist across all mobile and desktop devices.' }
                ],
                tips: 'Organize watchlists into distinct strategies (e.g. "Breakout Coils", "Earnings Momentum", "Dividend Compounders").'
            },
            'coverage': {
                title: 'Data Integrity, Price Series & Filing Registry',
                icon: '🗄️',
                dataSource: 'Internal database tables (price_history, earnings_history, ticker_metrics, universes) in SQLite/Turso.',
                what: 'Audit log of historical daily OHLCV prices, corporate earnings calendar entries, missing price bars, and Turso cloud database replication status.',
                thought: 'Quantitative backtesting and machine learning models are entirely dependent on point-in-time data cleanliness. Continuous verification of price continuity and filing timestamps prevents lookahead bias and data leakage.',
                calculations: [
                    { name: 'Price Bars Coverage %', formula: 'Tickers with ≥ 70 historical bars / Total Universe Count * 100%', desc: 'Percentage of universe with sufficient history to compute 63D features.' },
                    { name: 'Earnings Data Freshness', formula: 'Now() - max(fetched_at) timestamp in earnings_freshness', desc: 'Alerts if calendar data is older than 24 hours.' }
                ],
                tips: 'Master users can execute incremental refreshes to ingest missing earnings dates automatically.'
            },
            'industries': {
                title: 'Industry Sector Reactions & Cohort Performance',
                icon: '🏭',
                dataSource: 'Sector/Industry taxonomy database aggregated against event_dataset historical earnings reactions.',
                what: 'Historical 7-day post-earnings reaction distributions grouped by industry, ranking sectors by beat frequency and mean percentage gain.',
                thought: 'Upwards of 70% of single-stock variance is driven by macro and sector cohort momentum. Allocating capital exclusively to the top-quartile performing industries substantially boosts strategy Sharpe ratios.',
                calculations: [
                    { name: 'Mean Sector Reaction %', formula: 'Average 7-Day post-earnings return across all sector releases', desc: 'Quantifies whether the sector experiences broad institutional re-rating.' },
                    { name: 'Sector Beat Rate %', formula: 'Count(Positive Reactions in Sector) / Total Sector Releases * 100%', desc: 'Proportion of constituent companies outperforming expectations.' }
                ],
                tips: 'Prioritize individual stock longs in sectors where the cohort beat rate exceeds 70%.'
            },
            'patterns': {
                title: 'Algorithmic Technical Chart Patterns',
                icon: '📐',
                dataSource: 'Daily OHLCV series processed by automated geometric pattern recognition algorithms.',
                what: 'Algorithmic recognition of classical geometric patterns: Cup & Handle, Ascending Triangles, Double Bottoms, Flags, and Pennants with pivot confirmation.',
                thought: 'Structural chart patterns reflect the mechanical balance between supply and demand. Recognising apex compression in ascending triangles and cup-with-handle bases pinpoints optimal breakout timing.',
                calculations: [
                    { name: 'Pattern Quality Score (0-100)', formula: 'Geometric Symmetry + Volume Contraction in Base + Breakout Volume Expansion', desc: 'Scores structural validity; setups ≥ 70 offer highest reliability.' },
                    { name: 'Pivot Breakout Price', formula: 'Highest swing resistance boundary defining the pattern ceiling', desc: 'Price trigger that confirms pattern breakout on above-average volume.' }
                ],
                tips: 'Ensure breakout volume is at least 1.5x the 20-day average when price crosses the pivot level.'
            },
            'playground': {
                title: 'Quant API Playground & Interactive Sandbox',
                icon: '🧪',
                dataSource: 'Live FastAPI endpoints (/api/v1/*) with OpenAPI schema definitions and real-time execution payloads.',
                what: 'Interactive API console allowing live exploration of endpoints, parameters, JSON response schemas, and algorithmic execution payloads.',
                thought: 'Empowers developers and quantitative traders to prototype custom scripts, test edge-case payloads, and integrate Nexus APIs directly into external trading algorithms and bots.',
                calculations: [
                    { name: 'Execution Latency (ms)', formula: 'Client Request Timestamp to Complete Server Response (ms)', desc: 'Roundtrip execution time for algorithmic trading integration.' }
                ],
                tips: 'Use the playground to test custom query parameters before deploying algorithmic integrations.'
            }
        };

        app.openPageGuideModal = function(tabName) {
            let currentTab = tabName || app.currentTab;
            if (!currentTab) {
                const activeNav = document.querySelector('.sidebar-nav-item.active');
                if (activeNav) currentTab = activeNav.getAttribute('data-tab');
            }
            if (!currentTab) {
                const activeContent = document.querySelector('.tab-content.active');
                if (activeContent && activeContent.id) {
                    currentTab = activeContent.id.replace('tab-', '');
                }
            }
            if (!currentTab && window.location.hash) {
                currentTab = window.location.hash.replace('#', '').replace('tab=', '');
            }
            currentTab = (currentTab || 'home').toLowerCase();

            const guide = (app.PAGE_GUIDES && app.PAGE_GUIDES[currentTab]) 
                ? app.PAGE_GUIDES[currentTab] 
                : (app.PAGE_GUIDES ? (app.PAGE_GUIDES['home'] || app.PAGE_GUIDES['results']) : null);

            if (!guide) return;

            const modal = document.getElementById('pageGuideModal');
            const titleEl = document.getElementById('pageGuideTitle');
            const iconEl = document.getElementById('pageGuideIcon');
            const subtitleEl = document.getElementById('pageGuideSubtitle');
            const bodyEl = document.getElementById('pageGuideBody');

            if (titleEl) titleEl.textContent = guide.title;
            if (iconEl) iconEl.textContent = guide.icon || '💡';
            if (subtitleEl) subtitleEl.textContent = `Nexus Quantitative Architecture & Calculations (${currentTab.toUpperCase()})`;

            if (bodyEl) {
                let html = `
                    <!-- 1. What is this screen? -->
                    <div style="background: rgba(59,130,246,0.08); border: 1px solid rgba(59,130,246,0.25); padding: 0.85rem 1rem; border-radius: 8px;">
                        <div style="font-weight: 700; color: #60a5fa; margin-bottom: 0.25rem; font-size: 0.82rem; display: flex; align-items: center; gap: 0.35rem;">
                            <span>📋</span> What is on this screen?
                        </div>
                        <div style="color: #e2e8f0; font-size: 0.78rem; line-height: 1.5;">${guide.what}</div>
                    </div>

                    <!-- 2. Data Source & Pipeline -->
                    <div style="background: rgba(168,85,247,0.08); border: 1px solid rgba(168,85,247,0.25); padding: 0.85rem 1rem; border-radius: 8px;">
                        <div style="font-weight: 700; color: #c084fc; margin-bottom: 0.25rem; font-size: 0.82rem; display: flex; align-items: center; gap: 0.35rem;">
                            <span>📥</span> Data Source & Ingestion Pipeline
                        </div>
                        <div style="color: #e2e8f0; font-size: 0.78rem; line-height: 1.5;">${guide.dataSource}</div>
                    </div>

                    <!-- 3. Quantitative & Financial Thought -->
                    <div style="background: rgba(16,185,129,0.08); border: 1px solid rgba(16,185,129,0.25); padding: 0.85rem 1rem; border-radius: 8px;">
                        <div style="font-weight: 700; color: #34d399; margin-bottom: 0.25rem; font-size: 0.82rem; display: flex; align-items: center; gap: 0.35rem;">
                            <span>🧠</span> Quantitative & Financial Logic
                        </div>
                        <div style="color: #cbd5e1; font-size: 0.78rem; line-height: 1.5;">${guide.thought}</div>
                    </div>
                `;

                if (guide.calculations && guide.calculations.length > 0) {
                    html += `
                        <!-- 4. Parameter & Formula Calculations -->
                        <div style="background: rgba(15,23,42,0.85); border: 1px solid rgba(255,255,255,0.08); padding: 0.85rem 1rem; border-radius: 8px;">
                            <div style="font-weight: 700; color: #fbbf24; margin-bottom: 0.45rem; font-size: 0.82rem; display: flex; align-items: center; gap: 0.35rem;">
                                <span>📐</span> How Parameters & Formulas Are Calculated
                            </div>
                            <div style="display: flex; flex-direction: column; gap: 0.55rem;">
                                ${guide.calculations.map(m => `
                                    <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.06); padding: 0.5rem 0.75rem; border-radius: 6px;">
                                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 0.25rem; margin-bottom: 0.2rem;">
                                            <strong style="color: #f1f5f9; font-size: 0.78rem;">${m.name}</strong>
                                            <code style="background: rgba(0,0,0,0.4); color: #38bdf8; font-size: 0.7rem; padding: 0.1rem 0.35rem; border-radius: 3px; border: 1px solid rgba(56,189,248,0.25);">${m.formula}</code>
                                        </div>
                                        <div style="color: #94a3b8; font-size: 0.74rem; line-height: 1.4;">${m.desc}</div>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    `;
                }

                if (guide.tips) {
                    html += `
                        <!-- 5. Pro Trading Tip -->
                        <div style="background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.25); padding: 0.75rem 1rem; border-radius: 8px; font-size: 0.78rem; display: flex; align-items: flex-start; gap: 0.5rem;">
                            <span style="font-size: 1.1rem; line-height: 1;">💡</span>
                            <div>
                                <strong style="color: #fbbf24;">Actionable Decision Rule:</strong>
                                <span style="color: #fde68a;"> ${guide.tips}</span>
                            </div>
                        </div>
                    `;
                }

                bodyEl.innerHTML = html;
            }

            if (modal) modal.style.display = 'flex';
        };

        app.closePageGuideModal = function() {
            const modal = document.getElementById('pageGuideModal');
            if (modal) modal.style.display = 'none';
        };

        // Close guide modal on clicking outside or ESC key
        document.addEventListener('keydown', function(e) {
            if (e.key === 'Escape') {
                app.closePageGuideModal();
            }
        });

})(); // end page_guide IIFE

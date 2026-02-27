"""
I-Trade Strategy Executor
The brain: connects scanner signals to the paper trading engine.
Implements the 3 pillars: Momentum, Memecoin/Smart Money, Funding Arbitrage.
"""

import logging
import time
from dataclasses import dataclass

from market_data import MarketData
from paper_engine import PaperEngine, Strategy, Side
from memecoin_scanner import MemecoinScanner

logger = logging.getLogger("i-trade.executor")


@dataclass
class CandleStats:
    high_24h: float = 0
    low_24h: float = 0
    avg_volume_4h: float = 0
    current_volume_15m: float = 0
    rsi: float = 50
    price: float = 0


class StrategyExecutor:
    def __init__(self, engine: PaperEngine, market: MarketData, scanner: MemecoinScanner):
        self.engine = engine
        self.market = market
        self.scanner = scanner
        self._last_execution: dict[str, float] = {}  # coin -> timestamp, avoid duplicate entries
        self._cooldown = 300  # 5 min cooldown per coin

    def _on_cooldown(self, coin: str) -> bool:
        last = self._last_execution.get(coin, 0)
        return (time.time() - last) < self._cooldown

    def _mark_executed(self, coin: str):
        self._last_execution[coin] = time.time()

    def _coin_already_open(self, coin: str) -> bool:
        return any(t.coin == coin for t in self.engine.open_trades)

    # ── Pillar A: Momentum Breakout ─────────────────────────────

    async def _get_candle_stats(self, coin: str) -> CandleStats:
        """Calculate indicators from candle data."""
        try:
            candles = await self.market.get_candles(coin, "1h", limit=25)
            if not candles or len(candles) < 5:
                return CandleStats()

            closes = [float(c.get("c", 0)) for c in candles if c.get("c")]
            highs = [float(c.get("h", 0)) for c in candles if c.get("h")]
            lows = [float(c.get("l", 0)) for c in candles if c.get("l")]
            volumes = [float(c.get("v", 0)) for c in candles if c.get("v")]

            if not closes or not volumes:
                return CandleStats()

            # 24h high/low
            high_24h = max(highs[-24:]) if len(highs) >= 24 else max(highs)
            low_24h = min(lows[-24:]) if len(lows) >= 24 else min(lows)

            # Average volume over last 4h
            avg_vol_4h = sum(volumes[-4:]) / max(len(volumes[-4:]), 1)

            # Approximate 15m volume as 1/4 of last hourly
            current_vol_15m = volumes[-1] / 4 if volumes else 0

            # Simple RSI (14 periods)
            rsi = self._calc_rsi(closes)

            return CandleStats(
                high_24h=high_24h,
                low_24h=low_24h,
                avg_volume_4h=avg_vol_4h,
                current_volume_15m=current_vol_15m,
                rsi=rsi,
                price=closes[-1] if closes else 0,
            )
        except Exception as e:
            logger.warning("Failed to get candle stats for %s: %s", coin, e)
            return CandleStats()

    def _calc_rsi(self, closes: list[float], period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        recent = deltas[-period:]
        gains = [d for d in recent if d > 0]
        losses = [-d for d in recent if d < 0]
        avg_gain = sum(gains) / period if gains else 0
        avg_loss = sum(losses) / period if losses else 0.001
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    async def execute_momentum(self, rates: list[dict]):
        """Pillar A: Momentum Breakout — enter when price breaks 24h high with volume."""
        # Pick top volume coins that aren't already in position
        candidates = [r for r in rates if r["volume_24h"] > 500_000 and not self._coin_already_open(r["coin"]) and not self._on_cooldown(r["coin"])]
        candidates.sort(key=lambda r: r["volume_24h"], reverse=True)

        for candidate in candidates[:10]:  # Check top 10 by volume
            coin = candidate["coin"]
            stats = await self._get_candle_stats(coin)

            if stats.price <= 0 or stats.high_24h <= 0:
                continue

            signals = []

            # Signal 1: Volume spike (15m volume > 3x avg 4h volume / 4)
            if stats.avg_volume_4h > 0 and stats.current_volume_15m > (stats.avg_volume_4h / 4) * 3:
                signals.append(f"📊 Volume spike: {stats.current_volume_15m:.0f} vs avg {stats.avg_volume_4h / 4:.0f}")

            # Signal 2: Price near or above 24h high
            if stats.price >= stats.high_24h * 0.995:
                signals.append(f"🔺 Breakout 24h high: {stats.price:.4f} >= {stats.high_24h:.4f}")

            # Signal 3: RSI in sweet spot (55-75)
            if 55 <= stats.rsi <= 75:
                signals.append(f"📈 RSI {stats.rsi:.0f} (sweet spot)")

            # Need at least 2 signals
            if len(signals) >= 2:
                trade = self.engine.open_trade(
                    coin=coin,
                    strategy=Strategy.MOMENTUM,
                    side=Side.LONG,
                    entry_price=stats.price,
                    size_usdc=100,
                    leverage=1.0,
                    stop_loss_pct=4.0,
                    take_profit_levels=[
                        {"pct": 8, "close_pct": 50},
                        {"pct": 15, "close_pct": 30},
                    ],
                    trailing_stop_pct=5.0,
                    signals=signals,
                )
                if trade:
                    self._mark_executed(coin)
                    logger.info("MOMENTUM ENTRY: %s | %s", coin, " | ".join(signals))

    # ── Pillar B: Memecoin / Smart Money ────────────────────────

    async def execute_memecoin(self):
        """Pillar B: Enter memecoins based on scanner alerts with high score."""
        watchlist = self.scanner.get_watchlist()

        for alert in watchlist:
            coin = alert["coin"]
            score = alert["score"]

            if score < 3:
                continue
            if self._coin_already_open(coin):
                continue
            if self._on_cooldown(coin):
                continue
            if alert["red_flags"]:
                # Skip if there are red flags
                logger.info("MEMECOIN SKIP %s: red flags %s", coin, alert["red_flags"])
                continue
            if alert["volume_24h"] < 100_000:
                continue

            price = alert["price"]
            if price <= 0:
                continue

            trade = self.engine.open_trade(
                coin=coin,
                strategy=Strategy.MEMECOIN,
                side=Side.LONG,
                entry_price=price,
                size_usdc=75,
                leverage=1.0,
                stop_loss_pct=12.0,
                take_profit_levels=[
                    {"pct": 15, "close_pct": 50},
                ],
                trailing_stop_pct=8.0,
                max_duration_h=48,
                signals=alert["signals"],
            )
            if trade:
                self._mark_executed(coin)
                logger.info("MEMECOIN ENTRY: %s | score=%d | %s", coin, score, " | ".join(alert["signals"]))

    # ── Pillar C: Funding Rate Arbitrage ────────────────────────

    async def execute_funding(self, rates: list[dict]):
        """Pillar C: Enter when funding rate is extreme to collect funding."""
        for r in rates:
            coin = r["coin"]
            funding_ann = r["funding_annualized"]
            volume = r["volume_24h"]

            if abs(funding_ann) < 50:
                continue
            if volume < 1_000_000:
                continue
            if self._coin_already_open(coin):
                continue
            if self._on_cooldown(coin):
                continue

            price = r["mark_price"]
            if price <= 0:
                continue

            # Positive funding = shorts are paid -> go short
            # Negative funding = longs are paid -> go long
            side = Side.SHORT if funding_ann > 0 else Side.LONG
            direction = "SHORT (funding +)" if funding_ann > 0 else "LONG (funding -)"

            trade = self.engine.open_trade(
                coin=coin,
                strategy=Strategy.FUNDING,
                side=side,
                entry_price=price,
                size_usdc=150,
                leverage=2.0,
                stop_loss_pct=6.0,
                take_profit_levels=[
                    {"pct": 5, "close_pct": 100},
                ],
                trailing_stop_pct=None,
                max_duration_h=72,
                signals=[f"💰 Funding {funding_ann:.0f}% ann. → {direction}"],
            )
            if trade:
                self._mark_executed(coin)
                logger.info("FUNDING ENTRY: %s %s | funding=%.0f%% ann.", coin, direction, funding_ann)

    # ── Main execution cycle ────────────────────────────────────

    async def execute(self):
        """Run all 3 strategies. Called by the scan loop."""
        can_trade, reason = self.engine.check_risk()
        if not can_trade:
            logger.info("Trading paused: %s", reason)
            return

        try:
            # Get funding rates (used by momentum + funding pillars)
            rates = await self.market.get_funding_rates()

            # Execute all 3 pillars
            await self.execute_momentum(rates)
            await self.execute_memecoin()
            await self.execute_funding(rates)

        except Exception as e:
            logger.error("Strategy execution error: %s", e)

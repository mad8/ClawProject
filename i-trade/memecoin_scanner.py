"""
I-Trade Memecoin Scanner
Monitors smart money, whale activity, token distribution and narratives.
"""

import logging
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from market_data import MarketData

logger = logging.getLogger("i-trade.scanner")


@dataclass
class TokenAlert:
    coin: str
    score: int  # 0-5 signals matched
    signals: list[str]
    red_flags: list[str]
    price: float
    volume_24h: float
    volume_ratio: float
    funding_rate: float
    top_holders_pct: float
    is_new_listing: bool
    detected_at: float
    status: str = "watching"  # watching, entered, rejected

    def to_dict(self) -> dict:
        return asdict(self)


class MemecoinScanner:
    def __init__(self, market: MarketData):
        self.market = market
        self.known_coins: set[str] = set()
        self.alerts: list[TokenAlert] = []
        self.whale_wallets: dict[str, list[dict]] = {}  # coin -> whale trades
        self._initialized = False

    async def initialize(self):
        """Load initial coin list."""
        meta = await self.market.get_meta()
        self.known_coins = {a["name"] for a in meta.get("universe", [])}
        self._initialized = True
        logger.info("Scanner initialized with %d known coins", len(self.known_coins))

    async def scan(self) -> list[TokenAlert]:
        """Run a full scan cycle. Returns new alerts."""
        if not self._initialized:
            await self.initialize()

        new_alerts = []

        # 1. Check for new listings
        new_listings = await self.market.detect_new_listings(self.known_coins)
        for nl in new_listings:
            self.known_coins.add(nl["coin"])
            alert = TokenAlert(
                coin=nl["coin"],
                score=1,
                signals=["🆕 Nouveau listing détecté"],
                red_flags=[],
                price=nl["price"],
                volume_24h=0,
                volume_ratio=0,
                funding_rate=0,
                top_holders_pct=0,
                is_new_listing=True,
                detected_at=time.time(),
            )
            new_alerts.append(alert)
            logger.info("NEW LISTING: %s @ %.4f", nl["coin"], nl["price"])

        # 2. Volume spike detection
        spikes = await self.market.get_volume_spike_tokens(threshold=2.5)
        for spike in spikes:
            existing = next((a for a in self.alerts if a.coin == spike["coin"]), None)
            if existing and time.time() - existing.detected_at < 3600:
                continue

            signals = []
            red_flags = []
            score = 0

            # Signal: Volume spike
            if spike["volume_ratio"] >= 3.0:
                signals.append(f"📊 Volume x{spike['volume_ratio']} vs veille")
                score += 1
            if spike["volume_ratio"] >= 5.0:
                signals.append("🔥 Volume extrême (x5+)")
                score += 1

            # Signal: Whale trades
            whale_data = await self._check_whale_activity(spike["coin"])
            if whale_data["whale_count"] >= 3:
                signals.append(f"🐋 {whale_data['whale_count']} gros trades détectés ({whale_data['total_volume']:.0f} USDC)")
                score += 1
            if whale_data["whale_count"] >= 5:
                signals.append("🐋🐋 Activité whale massive")
                score += 1

            # Signal: Funding rate extreme
            funding_ann = spike["funding_rate"] * 3 * 365 * 100
            if abs(funding_ann) > 50:
                signals.append(f"💰 Funding rate extrême: {funding_ann:.0f}% annualisé")
                score += 1

            # Red flags
            if spike["volume_24h"] < 100_000:
                red_flags.append("⚠️ Volume 24h faible (<100k USDC)")
            if whale_data.get("concentration_high"):
                red_flags.append("⚠️ Concentration élevée détectée dans les trades")

            if score >= 2:
                alert = TokenAlert(
                    coin=spike["coin"],
                    score=score,
                    signals=signals,
                    red_flags=red_flags,
                    price=spike["mark_price"],
                    volume_24h=spike["volume_24h"],
                    volume_ratio=spike["volume_ratio"],
                    funding_rate=spike["funding_rate"],
                    top_holders_pct=whale_data.get("top_concentration", 0),
                    is_new_listing=False,
                    detected_at=time.time(),
                )
                new_alerts.append(alert)
                logger.info("ALERT: %s | score=%d | %s", spike["coin"], score, ", ".join(signals))

        # 3. Funding rate opportunities
        rates = await self.market.get_funding_rates()
        for r in rates:
            if abs(r["funding_annualized"]) > 50 and r["volume_24h"] > 1_000_000:
                existing = next((a for a in self.alerts if a.coin == r["coin"]), None)
                if existing and time.time() - existing.detected_at < 7200:
                    continue

                direction = "SHORT (funding positif)" if r["funding_annualized"] > 0 else "LONG (funding négatif)"
                alert = TokenAlert(
                    coin=r["coin"],
                    score=1,
                    signals=[f"💰 Funding arbitrage: {r['funding_annualized']:.0f}% ann. → {direction}"],
                    red_flags=[],
                    price=r["mark_price"],
                    volume_24h=r["volume_24h"],
                    volume_ratio=0,
                    funding_rate=r["funding_rate"],
                    top_holders_pct=0,
                    is_new_listing=False,
                    detected_at=time.time(),
                )
                new_alerts.append(alert)

        self.alerts.extend(new_alerts)
        # Keep only last 200 alerts
        if len(self.alerts) > 200:
            self.alerts = self.alerts[-200:]

        return new_alerts

    async def _check_whale_activity(self, coin: str) -> dict:
        """Analyze recent trades for whale activity."""
        trades = await self.market.get_recent_trades(coin)
        if not trades:
            return {"whale_count": 0, "total_volume": 0, "concentration_high": False, "top_concentration": 0}

        # Detect large trades (top 5% by size)
        sizes = [abs(float(t.get("sz", 0))) * float(t.get("px", 0)) for t in trades if t.get("sz")]
        if not sizes:
            return {"whale_count": 0, "total_volume": 0, "concentration_high": False, "top_concentration": 0}

        avg_size = sum(sizes) / len(sizes)
        whale_threshold = avg_size * 5
        whales = [s for s in sizes if s > whale_threshold]

        total_vol = sum(sizes)
        whale_vol = sum(whales)
        concentration = (whale_vol / total_vol * 100) if total_vol > 0 else 0

        return {
            "whale_count": len(whales),
            "total_volume": whale_vol,
            "concentration_high": concentration > 60,
            "top_concentration": round(concentration, 1),
        }

    def get_watchlist(self) -> list[dict]:
        """Get current watchlist sorted by score."""
        # Only recent alerts (last 24h)
        cutoff = time.time() - 86400
        recent = [a for a in self.alerts if a.detected_at > cutoff]
        recent.sort(key=lambda a: (a.score, a.volume_ratio), reverse=True)
        return [a.to_dict() for a in recent[:50]]

    def get_stats(self) -> dict:
        cutoff = time.time() - 86400
        recent = [a for a in self.alerts if a.detected_at > cutoff]
        return {
            "total_alerts_24h": len(recent),
            "high_score_alerts": len([a for a in recent if a.score >= 3]),
            "new_listings_24h": len([a for a in recent if a.is_new_listing]),
            "known_coins": len(self.known_coins),
            "last_scan": time.time(),
        }

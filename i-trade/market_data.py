"""
I-Trade Market Data
Fetches live data from Hyperliquid public API.
"""

import logging
import time
from typing import Optional

import httpx

from config import Config

logger = logging.getLogger("i-trade.market")


class MarketData:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15)
        self.base_url = Config.HL_INFO_URL
        self._cache: dict = {}
        self._cache_ts: dict = {}

    async def _post(self, payload: dict) -> dict | list:
        resp = await self.client.post(self.base_url, json=payload)
        resp.raise_for_status()
        return resp.json()

    # ── Market overview ─────────────────────────────────────────

    async def get_all_mids(self) -> dict[str, float]:
        """Get mid prices for all assets."""
        data = await self._post({"type": "allMids"})
        return {k: float(v) for k, v in data.items()}

    async def get_meta(self) -> dict:
        """Get exchange metadata (all listed assets)."""
        return await self._post({"type": "meta"})

    async def get_meta_and_asset_ctxs(self) -> tuple[dict, list]:
        """Get metadata + asset contexts (funding, volume, open interest)."""
        data = await self._post({"type": "metaAndAssetCtxs"})
        return data[0], data[1]

    # ── Specific asset ──────────────────────────────────────────

    async def get_candles(self, coin: str, interval: str = "1h", limit: int = 100) -> list[dict]:
        """Get candle data. interval: 1m, 5m, 15m, 1h, 4h, 1d"""
        data = await self._post({
            "type": "candleSnapshot",
            "req": {"coin": coin, "interval": interval, "startTime": int((time.time() - limit * 3600) * 1000)}
        })
        return data

    async def get_l2_book(self, coin: str) -> dict:
        """Get L2 order book."""
        return await self._post({"type": "l2Book", "coin": coin})

    # ── Funding rates ───────────────────────────────────────────

    async def get_funding_rates(self) -> list[dict]:
        """Get current funding rates for all perps."""
        meta, ctxs = await self.get_meta_and_asset_ctxs()
        assets = meta.get("universe", [])
        rates = []
        for i, asset in enumerate(assets):
            if i < len(ctxs):
                ctx = ctxs[i]
                funding = float(ctx.get("funding", "0"))
                volume = float(ctx.get("dayNtlVlm", "0"))
                open_interest = float(ctx.get("openInterest", "0"))
                mark_price = float(ctx.get("markPx", "0"))
                rates.append({
                    "coin": asset["name"],
                    "funding_rate": funding,
                    "funding_annualized": funding * 3 * 365 * 100,  # 8h funding * 3 * 365
                    "volume_24h": volume,
                    "open_interest": open_interest,
                    "mark_price": mark_price,
                })
        return rates

    # ── Smart money / whale detection ───────────────────────────

    async def get_recent_trades(self, coin: str, limit: int = 200) -> list[dict]:
        """Get recent trades for whale detection."""
        # Hyperliquid public trades endpoint
        try:
            resp = await self.client.post(self.base_url, json={
                "type": "recentTrades",
                "coin": coin,
            })
            resp.raise_for_status()
            trades = resp.json()
            return trades[:limit]
        except Exception as e:
            logger.warning("Failed to get recent trades for %s: %s", coin, e)
            return []

    # ── Volume analysis ─────────────────────────────────────────

    async def get_volume_spike_tokens(self, threshold: float = 3.0) -> list[dict]:
        """Detect tokens with volume spikes."""
        meta, ctxs = await self.get_meta_and_asset_ctxs()
        assets = meta.get("universe", [])
        spikes = []
        for i, asset in enumerate(assets):
            if i < len(ctxs):
                ctx = ctxs[i]
                volume = float(ctx.get("dayNtlVlm", "0"))
                prev_volume = float(ctx.get("prevDayNtlVlm", "0")) if "prevDayNtlVlm" in ctx else 0
                mark_price = float(ctx.get("markPx", "0"))
                if prev_volume > 0 and volume / prev_volume > threshold:
                    spikes.append({
                        "coin": asset["name"],
                        "volume_24h": volume,
                        "prev_volume_24h": prev_volume,
                        "volume_ratio": round(volume / prev_volume, 2),
                        "mark_price": mark_price,
                        "funding_rate": float(ctx.get("funding", "0")),
                    })
        spikes.sort(key=lambda x: x["volume_ratio"], reverse=True)
        return spikes

    # ── New listings detection ──────────────────────────────────

    async def detect_new_listings(self, known_coins: set[str]) -> list[dict]:
        """Detect newly listed coins."""
        meta = await self.get_meta()
        current_coins = {a["name"] for a in meta.get("universe", [])}
        new_coins = current_coins - known_coins
        results = []
        if new_coins:
            mids = await self.get_all_mids()
            for coin in new_coins:
                results.append({
                    "coin": coin,
                    "price": mids.get(coin, 0),
                    "detected_at": time.time(),
                })
        return results

    async def close(self):
        await self.client.aclose()

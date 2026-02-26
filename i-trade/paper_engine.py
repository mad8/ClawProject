"""
I-Trade Paper Trading Engine
Simulates trades with real market data.
"""

import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

from config import Config

logger = logging.getLogger("i-trade.engine")


class Strategy(str, Enum):
    MOMENTUM = "momentum"
    MEMECOIN = "memecoin"
    FUNDING = "funding"


class Side(str, Enum):
    LONG = "long"
    SHORT = "short"


class TradeStatus(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class CloseReason(str, Enum):
    TAKE_PROFIT = "take_profit"
    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TIMEOUT = "timeout"
    MANUAL = "manual"
    DAILY_LIMIT = "daily_limit"


@dataclass
class Trade:
    id: str
    coin: str
    strategy: Strategy
    side: Side
    entry_price: float
    size_usdc: float
    leverage: float
    stop_loss_pct: float
    take_profit_levels: list[dict]  # [{"pct": 8, "close_pct": 50}, ...]
    trailing_stop_pct: Optional[float]
    max_duration_h: Optional[float]
    status: TradeStatus = TradeStatus.OPEN
    entry_time: float = 0
    exit_price: float = 0
    exit_time: float = 0
    close_reason: Optional[CloseReason] = None
    pnl: float = 0
    pnl_pct: float = 0
    highest_price: float = 0
    lowest_price: float = 0
    remaining_size_pct: float = 100
    signals: list[str] = field(default_factory=list)
    partial_exits: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["strategy"] = self.strategy.value
        d["side"] = self.side.value
        d["status"] = self.status.value
        if self.close_reason:
            d["close_reason"] = self.close_reason.value
        return d


class PaperEngine:
    def __init__(self):
        self.initial_balance = Config.INITIAL_BALANCE
        self.balance = Config.INITIAL_BALANCE
        self.trades: list[Trade] = []
        self.open_trades: list[Trade] = []
        self.daily_pnl: dict[str, float] = {}  # "YYYY-MM-DD" -> pnl
        self.peak_balance = Config.INITIAL_BALANCE
        self.paused = False
        self.pause_reason = ""
        self._alerts: list[dict] = []

    # ── Portfolio state ─────────────────────────────────────────

    @property
    def total_invested(self) -> float:
        return sum(t.size_usdc * (t.remaining_size_pct / 100) for t in self.open_trades)

    @property
    def cash_available(self) -> float:
        return self.balance - self.total_invested

    @property
    def cash_ratio(self) -> float:
        return self.cash_available / self.balance if self.balance > 0 else 0

    @property
    def total_pnl(self) -> float:
        return self.balance - self.initial_balance

    @property
    def total_pnl_pct(self) -> float:
        return (self.total_pnl / self.initial_balance) * 100

    @property
    def drawdown(self) -> float:
        return self.peak_balance - self.balance

    @property
    def drawdown_pct(self) -> float:
        return (self.drawdown / self.peak_balance) * 100 if self.peak_balance > 0 else 0

    @property
    def win_rate(self) -> float:
        closed = [t for t in self.trades if t.status == TradeStatus.CLOSED]
        if not closed:
            return 0
        wins = sum(1 for t in closed if t.pnl > 0)
        return (wins / len(closed)) * 100

    @property
    def profit_factor(self) -> float:
        closed = [t for t in self.trades if t.status == TradeStatus.CLOSED]
        gains = sum(t.pnl for t in closed if t.pnl > 0)
        losses = abs(sum(t.pnl for t in closed if t.pnl < 0))
        return gains / losses if losses > 0 else float("inf") if gains > 0 else 0

    def get_today_key(self) -> str:
        return time.strftime("%Y-%m-%d")

    def get_daily_pnl_today(self) -> float:
        return self.daily_pnl.get(self.get_today_key(), 0)

    # ── Risk checks ─────────────────────────────────────────────

    def check_risk(self) -> tuple[bool, str]:
        if self.paused:
            return False, f"Trading paused: {self.pause_reason}"
        if abs(self.get_daily_pnl_today()) >= Config.MAX_DAILY_LOSS:
            self.paused = True
            self.pause_reason = f"Daily loss limit reached ({Config.MAX_DAILY_LOSS} USDC)"
            return False, self.pause_reason
        if self.drawdown >= Config.MAX_DRAWDOWN:
            self.paused = True
            self.pause_reason = f"Max drawdown reached ({Config.MAX_DRAWDOWN} USDC)"
            return False, self.pause_reason
        if len(self.open_trades) >= Config.MAX_OPEN_POSITIONS:
            return False, f"Max open positions ({Config.MAX_OPEN_POSITIONS})"
        if self.cash_ratio < Config.MIN_CASH_RATIO:
            return False, f"Cash ratio too low ({self.cash_ratio:.0%} < {Config.MIN_CASH_RATIO:.0%})"
        return True, "ok"

    # ── Open trade ──────────────────────────────────────────────

    def open_trade(
        self,
        coin: str,
        strategy: Strategy,
        side: Side,
        entry_price: float,
        size_usdc: float,
        leverage: float = 1.0,
        stop_loss_pct: float = 4.0,
        take_profit_levels: list[dict] | None = None,
        trailing_stop_pct: float | None = None,
        max_duration_h: float | None = None,
        signals: list[str] | None = None,
    ) -> Optional[Trade]:
        can_trade, reason = self.check_risk()
        if not can_trade:
            logger.warning("Trade blocked: %s", reason)
            self._alerts.append({
                "type": "blocked",
                "coin": coin,
                "reason": reason,
                "time": time.time(),
            })
            return None

        if size_usdc > self.cash_available:
            logger.warning("Insufficient cash: need %.2f, have %.2f", size_usdc, self.cash_available)
            return None

        trade = Trade(
            id=str(uuid.uuid4())[:8],
            coin=coin,
            strategy=strategy,
            side=side,
            entry_price=entry_price,
            size_usdc=size_usdc,
            leverage=leverage,
            stop_loss_pct=stop_loss_pct,
            take_profit_levels=take_profit_levels or [],
            trailing_stop_pct=trailing_stop_pct,
            max_duration_h=max_duration_h,
            entry_time=time.time(),
            highest_price=entry_price,
            lowest_price=entry_price,
            signals=signals or [],
        )
        self.open_trades.append(trade)
        self.trades.append(trade)

        logger.info(
            "OPEN %s %s %s @ %.4f | size=%.2f USDC | strategy=%s",
            trade.id, side.value.upper(), coin, entry_price, size_usdc, strategy.value,
        )
        self._alerts.append({
            "type": "open",
            "trade": trade.to_dict(),
            "time": time.time(),
        })
        return trade

    # ── Update prices / check exits ─────────────────────────────

    def update_trade(self, trade: Trade, current_price: float) -> Optional[CloseReason]:
        if trade.status != TradeStatus.OPEN:
            return None

        # Track high/low
        trade.highest_price = max(trade.highest_price, current_price)
        trade.lowest_price = min(trade.lowest_price, current_price)

        # Calculate current PnL
        if trade.side == Side.LONG:
            pnl_pct = ((current_price - trade.entry_price) / trade.entry_price) * 100
        else:
            pnl_pct = ((trade.entry_price - current_price) / trade.entry_price) * 100

        pnl_pct *= trade.leverage

        # Check stop loss
        if pnl_pct <= -trade.stop_loss_pct:
            return self._close_trade(trade, current_price, CloseReason.STOP_LOSS)

        # Check take profit levels
        for tp in trade.take_profit_levels:
            if pnl_pct >= tp["pct"] and not tp.get("triggered"):
                close_amount = trade.size_usdc * (tp["close_pct"] / 100) * (trade.remaining_size_pct / 100)
                partial_pnl = close_amount * (pnl_pct / 100)
                trade.remaining_size_pct -= tp["close_pct"]
                tp["triggered"] = True
                trade.partial_exits.append({
                    "pct": tp["pct"],
                    "close_pct": tp["close_pct"],
                    "price": current_price,
                    "pnl": partial_pnl,
                    "time": time.time(),
                })
                self.balance += partial_pnl
                logger.info("PARTIAL TP %s: +%.1f%% | closed %.0f%% | pnl=%.2f",
                            trade.id, tp["pct"], tp["close_pct"], partial_pnl)

        # Check trailing stop
        if trade.trailing_stop_pct and trade.remaining_size_pct > 0:
            if trade.side == Side.LONG:
                trail_pct = ((trade.highest_price - current_price) / trade.highest_price) * 100
            else:
                trail_pct = ((current_price - trade.lowest_price) / trade.lowest_price) * 100
            if trail_pct >= trade.trailing_stop_pct:
                return self._close_trade(trade, current_price, CloseReason.TRAILING_STOP)

        # Check timeout
        if trade.max_duration_h:
            elapsed_h = (time.time() - trade.entry_time) / 3600
            if elapsed_h >= trade.max_duration_h:
                return self._close_trade(trade, current_price, CloseReason.TIMEOUT)

        # If all TPs triggered and no remaining size
        if trade.remaining_size_pct <= 0:
            return self._close_trade(trade, current_price, CloseReason.TAKE_PROFIT)

        return None

    def _close_trade(self, trade: Trade, exit_price: float, reason: CloseReason) -> CloseReason:
        if trade.side == Side.LONG:
            pnl_pct = ((exit_price - trade.entry_price) / trade.entry_price) * 100
        else:
            pnl_pct = ((trade.entry_price - exit_price) / trade.entry_price) * 100

        pnl_pct *= trade.leverage
        remaining_size = trade.size_usdc * (trade.remaining_size_pct / 100)
        final_pnl = remaining_size * (pnl_pct / 100)

        # Add partial exits PnL
        partial_pnl = sum(p["pnl"] for p in trade.partial_exits)
        total_pnl = final_pnl + partial_pnl

        trade.status = TradeStatus.CLOSED
        trade.exit_price = exit_price
        trade.exit_time = time.time()
        trade.close_reason = reason
        trade.pnl = total_pnl
        trade.pnl_pct = (total_pnl / trade.size_usdc) * 100

        self.balance += final_pnl
        self.peak_balance = max(self.peak_balance, self.balance)

        today = self.get_today_key()
        self.daily_pnl[today] = self.daily_pnl.get(today, 0) + total_pnl

        if trade in self.open_trades:
            self.open_trades.remove(trade)

        logger.info(
            "CLOSE %s %s %s @ %.4f | reason=%s | pnl=%.2f (%.1f%%)",
            trade.id, trade.side.value.upper(), trade.coin,
            exit_price, reason.value, total_pnl, trade.pnl_pct,
        )
        self._alerts.append({
            "type": "close",
            "trade": trade.to_dict(),
            "time": time.time(),
        })
        return reason

    # ── Alerts ──────────────────────────────────────────────────

    def pop_alerts(self) -> list[dict]:
        alerts = self._alerts.copy()
        self._alerts.clear()
        return alerts

    # ── Stats ───────────────────────────────────────────────────

    def get_stats(self) -> dict:
        closed = [t for t in self.trades if t.status == TradeStatus.CLOSED]
        wins = [t for t in closed if t.pnl > 0]
        losses = [t for t in closed if t.pnl <= 0]

        return {
            "balance": round(self.balance, 2),
            "initial_balance": self.initial_balance,
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "cash_available": round(self.cash_available, 2),
            "total_invested": round(self.total_invested, 2),
            "cash_ratio": round(self.cash_ratio * 100, 1),
            "peak_balance": round(self.peak_balance, 2),
            "drawdown": round(self.drawdown, 2),
            "drawdown_pct": round(self.drawdown_pct, 2),
            "daily_pnl_today": round(self.get_daily_pnl_today(), 2),
            "total_trades": len(self.trades),
            "open_trades": len(self.open_trades),
            "closed_trades": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(self.win_rate, 1),
            "profit_factor": round(self.profit_factor, 2),
            "best_trade": round(max((t.pnl for t in closed), default=0), 2),
            "worst_trade": round(min((t.pnl for t in closed), default=0), 2),
            "avg_win": round(sum(t.pnl for t in wins) / len(wins), 2) if wins else 0,
            "avg_loss": round(sum(t.pnl for t in losses) / len(losses), 2) if losses else 0,
            "paused": self.paused,
            "pause_reason": self.pause_reason,
            "daily_pnl_history": self.daily_pnl,
            "strategy_breakdown": self._strategy_breakdown(closed),
        }

    def _strategy_breakdown(self, closed: list[Trade]) -> dict:
        breakdown = {}
        for strat in Strategy:
            strat_trades = [t for t in closed if t.strategy == strat]
            if strat_trades:
                wins = sum(1 for t in strat_trades if t.pnl > 0)
                breakdown[strat.value] = {
                    "trades": len(strat_trades),
                    "pnl": round(sum(t.pnl for t in strat_trades), 2),
                    "win_rate": round((wins / len(strat_trades)) * 100, 1),
                }
            else:
                breakdown[strat.value] = {"trades": 0, "pnl": 0, "win_rate": 0}
        return breakdown

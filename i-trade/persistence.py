"""
I-Trade Persistence
Save/load engine state to disk so trades survive restarts.
"""

import json
import logging
import os
import time

logger = logging.getLogger("i-trade.persistence")

STATE_FILE = os.path.join(os.path.dirname(__file__), "state.json")


def save_state(engine) -> bool:
    """Save engine state to disk."""
    try:
        data = {
            "saved_at": time.time(),
            "balance": engine.balance,
            "initial_balance": engine.initial_balance,
            "peak_balance": engine.peak_balance,
            "paused": engine.paused,
            "pause_reason": engine.pause_reason,
            "daily_pnl": engine.daily_pnl,
            "trades": [t.to_dict() for t in engine.trades],
        }
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, STATE_FILE)
        return True
    except Exception as e:
        logger.error("Failed to save state: %s", e)
        return False


def load_state(engine) -> bool:
    """Load engine state from disk."""
    if not os.path.exists(STATE_FILE):
        logger.info("No state file found, starting fresh")
        return False

    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        from paper_engine import Trade, Strategy, Side, TradeStatus, CloseReason

        engine.balance = data.get("balance", engine.initial_balance)
        engine.initial_balance = data.get("initial_balance", engine.initial_balance)
        engine.peak_balance = data.get("peak_balance", engine.balance)
        engine.paused = data.get("paused", False)
        engine.pause_reason = data.get("pause_reason", "")
        engine.daily_pnl = data.get("daily_pnl", {})
        engine.trades = []
        engine.open_trades = []

        for td in data.get("trades", []):
            trade = Trade(
                id=td["id"],
                coin=td["coin"],
                strategy=Strategy(td["strategy"]),
                side=Side(td["side"]),
                entry_price=td["entry_price"],
                size_usdc=td["size_usdc"],
                leverage=td["leverage"],
                stop_loss_pct=td["stop_loss_pct"],
                take_profit_levels=td.get("take_profit_levels", []),
                trailing_stop_pct=td.get("trailing_stop_pct"),
                max_duration_h=td.get("max_duration_h"),
                status=TradeStatus(td["status"]),
                entry_time=td.get("entry_time", 0),
                exit_price=td.get("exit_price", 0),
                exit_time=td.get("exit_time", 0),
                close_reason=CloseReason(td["close_reason"]) if td.get("close_reason") else None,
                pnl=td.get("pnl", 0),
                pnl_pct=td.get("pnl_pct", 0),
                highest_price=td.get("highest_price", td["entry_price"]),
                lowest_price=td.get("lowest_price", td["entry_price"]),
                remaining_size_pct=td.get("remaining_size_pct", 100),
                signals=td.get("signals", []),
                partial_exits=td.get("partial_exits", []),
            )
            engine.trades.append(trade)
            if trade.status == TradeStatus.OPEN:
                engine.open_trades.append(trade)

        saved_at = data.get("saved_at", 0)
        age = time.time() - saved_at
        logger.info(
            "State loaded: balance=$%.2f, %d trades (%d open), saved %.0fs ago",
            engine.balance, len(engine.trades), len(engine.open_trades), age,
        )
        return True

    except Exception as e:
        logger.error("Failed to load state: %s", e)
        return False

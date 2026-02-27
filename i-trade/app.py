"""
I-Trade Main Application
FastAPI server with WebSocket for live dashboard updates.
"""

import asyncio
import json
import logging
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from config import Config
from market_data import MarketData
from paper_engine import PaperEngine, Strategy, Side
from memecoin_scanner import MemecoinScanner
from strategy_executor import StrategyExecutor
from persistence import save_state, load_state

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
)
logger = logging.getLogger("i-trade.app")

# Global state
market = MarketData()
engine = PaperEngine()
scanner = MemecoinScanner(market)
executor = StrategyExecutor(engine, market, scanner)
connected_ws: list[WebSocket] = []
scan_task: asyncio.Task | None = None


async def broadcast(data: dict):
    """Broadcast data to all connected WebSocket clients."""
    msg = json.dumps(data)
    disconnected = []
    for ws in connected_ws:
        try:
            await ws.send_text(msg)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        connected_ws.remove(ws)


async def scan_loop():
    """Background loop: scan market, update trades, broadcast."""
    await asyncio.sleep(3)  # Wait for startup
    load_state(engine)
    await scanner.initialize()
    save_counter = 0

    while True:
        try:
            # Update prices for open trades
            if engine.open_trades:
                mids = await market.get_all_mids()
                for trade in list(engine.open_trades):
                    price = mids.get(trade.coin, 0)
                    if price > 0:
                        engine.update_trade(trade, price)

            # Run memecoin scanner
            new_alerts = await scanner.scan()

            # Execute strategies (the brain)
            await executor.execute()

            # Broadcast updates
            await broadcast({
                "type": "update",
                "stats": engine.get_stats(),
                "open_trades": [t.to_dict() for t in engine.open_trades],
                "scanner": scanner.get_stats(),
                "watchlist": scanner.get_watchlist(),
                "alerts": engine.pop_alerts(),
                "prices": await market.get_all_mids(),
                "timestamp": time.time(),
            })

            # Save state every 4 cycles (~60s)
            save_counter += 1
            if save_counter % 4 == 0:
                save_state(engine)

        except Exception as e:
            logger.error("Scan loop error: %s", e)

        await asyncio.sleep(15)  # Scan every 15 seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    global scan_task
    scan_task = asyncio.create_task(scan_loop())
    logger.info("I-Trade started on %s:%d", Config.HOST, Config.PORT)
    yield
    save_state(engine)
    logger.info("State saved on shutdown")
    if scan_task:
        scan_task.cancel()
    await market.close()


app = FastAPI(title="I-Trade Paper Trading", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")


# ── REST endpoints ──────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse("static/index.html")


@app.get("/api/stats")
async def get_stats():
    return engine.get_stats()


@app.get("/api/trades")
async def get_trades():
    return {
        "open": [t.to_dict() for t in engine.open_trades],
        "closed": [t.to_dict() for t in engine.trades if t.status.value == "closed"],
    }


@app.get("/api/trades/{trade_id}")
async def get_trade(trade_id: str):
    trade = next((t for t in engine.trades if t.id == trade_id), None)
    if not trade:
        return {"error": "Trade not found"}
    return trade.to_dict()


@app.get("/api/scanner/watchlist")
async def get_watchlist():
    return scanner.get_watchlist()


@app.get("/api/scanner/stats")
async def get_scanner_stats():
    return scanner.get_stats()


@app.get("/api/funding")
async def get_funding():
    rates = await market.get_funding_rates()
    rates.sort(key=lambda r: abs(r["funding_annualized"]), reverse=True)
    return rates[:30]


@app.get("/api/volume-spikes")
async def get_volume_spikes():
    return await market.get_volume_spike_tokens(threshold=2.0)


# ── WebSocket ───────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    connected_ws.append(ws)
    logger.info("WebSocket client connected (%d total)", len(connected_ws))

    # Send initial state
    try:
        await ws.send_text(json.dumps({
            "type": "init",
            "stats": engine.get_stats(),
            "open_trades": [t.to_dict() for t in engine.open_trades],
            "closed_trades": [t.to_dict() for t in engine.trades if t.status.value == "closed"],
            "scanner": scanner.get_stats(),
            "watchlist": scanner.get_watchlist(),
        }))
    except Exception:
        pass

    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        if ws in connected_ws:
            connected_ws.remove(ws)
        logger.info("WebSocket client disconnected (%d remaining)", len(connected_ws))


# ── Main ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=Config.HOST, port=Config.PORT)

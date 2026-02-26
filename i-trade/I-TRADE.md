# I-Trade 💀 — Paper Trading Bot + Dashboard

> Simulation de trading sur Hyperliquid avec données réelles, stratégie mixte, et surveillance memecoins en live.

---

## 🎯 Stratégie

### 3 Piliers

| Pilier | Allocation | Style |
|---|---|---|
| **A — Momentum Breakout** | 40% ($400) | Casser les résistances avec du volume |
| **B — Memecoins / Smart Money** | 30% ($300) | Suivre les whales et le smart money |
| **C — Funding Rate Arbitrage** | 30% ($300) | Collecter le funding rate extrême |

### Gestion du risque

| Règle | Valeur |
|---|---|
| Perte max par trade | -10% de la position |
| Perte max quotidienne | -$50 → pause 24h |
| Drawdown max total | -$150 → arrêt complet |
| Max positions ouvertes | 5 |
| Cash minimum | 30% du capital |

### Objectifs de validation (2 semaines)

| Métrique | Objectif |
|---|---|
| Win rate | > 55% |
| Profit factor | > 1.5 |
| Max drawdown | < 15% |
| Nombre de trades | > 20 |

---

## 📊 Dashboard

4 onglets :

1. **Overview** — Balance, PnL, win rate, drawdown, breakdown par stratégie, alertes live
2. **Trades** — Positions ouvertes (PnL temps réel) + historique complet
3. **Scanner** — Watchlist memecoins : score, signaux smart money, red flags, volume
4. **Funding** — Funding rates de tous les perps Hyperliquid, opportunités d'arbitrage

Connexion WebSocket pour mise à jour **live** toutes les 15 secondes.

---

## 🔍 Scanner Memecoins

Le scanner surveille en continu :

| Signal | Description |
|---|---|
| 🐋 Whale activity | Gros trades détectés (5x la moyenne) |
| 📊 Volume spike | Volume > 2.5x la veille |
| 🆕 Nouveau listing | Token fraîchement listé sur Hyperliquid |
| 💰 Funding extrême | Funding rate annualisé > 50% |

Chaque token reçoit un **score de 0 à 5** basé sur le nombre de signaux confirmés.

**Red flags automatiques :**
- Volume 24h < 100k USDC
- Concentration whale > 60% des trades

---

## ⚡ Installation

```bash
cd i-trade
cp .env.example .env
pip install -r requirements.txt
python app.py
```

Dashboard accessible sur : **http://localhost:8888**

### Avec Docker

```bash
docker build -t i-trade .
docker run -p 8888:8888 --env-file .env i-trade
```

---

## 📁 Structure

```
i-trade/
├── app.py                 # Serveur FastAPI + WebSocket
├── config.py              # Configuration
├── market_data.py         # Client API Hyperliquid (données live)
├── paper_engine.py        # Moteur paper trading (simulation)
├── memecoin_scanner.py    # Scanner memecoins / smart money
├── requirements.txt       # Dépendances Python
├── Dockerfile             # Image Docker
├── .env.example           # Template config
├── static/
│   └── index.html         # Dashboard web
└── I-TRADE.md             # Cette documentation
```

---

## 🔌 API Endpoints

| Méthode | Route | Description |
|---|---|---|
| GET | `/` | Dashboard web |
| GET | `/api/stats` | Stats globales (balance, PnL, win rate...) |
| GET | `/api/trades` | Positions ouvertes + historique |
| GET | `/api/trades/{id}` | Détail d'un trade |
| GET | `/api/scanner/watchlist` | Watchlist memecoins |
| GET | `/api/scanner/stats` | Stats du scanner |
| GET | `/api/funding` | Funding rates (top 30) |
| GET | `/api/volume-spikes` | Tokens avec spike de volume |
| WS | `/ws` | WebSocket live updates |

---

## 🚀 Roadmap

- [ ] Phase 1 : Paper trading + dashboard ← **ACTUEL**
- [ ] Phase 2 : Alertes Telegram en temps réel
- [ ] Phase 3 : Backtesting sur données historiques
- [ ] Phase 4 : Passage en réel via wallet agent Hyperliquid

---

*Développé par Vendredi 💀*

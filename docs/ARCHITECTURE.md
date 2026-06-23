# Architecture de l'écosystème

> Schéma des postes (data / cerveau / risque / labo / connaissance / UI) et de
> leurs liaisons. Tout est **lecture seule / advisory par défaut** : aucun ordre
> réel n'est passé sans la couche risque.

## Vue Mermaid (se rend sur GitHub)

```mermaid
flowchart TD
  subgraph DEPLOY["Déploiement"]
    VPS["VPS (principal)"]
    TERMUX["Termux (fournisseur de signaux)"]
    PCDRIVE["PC + Drive Desktop (G:)"]
    MCP["MCP (analyse / cette session)"]
  end

  subgraph SOURCES["Sources de données (perception)"]
    BG["Bitget REST"]
    CG["CoinGecko (repli)"]
    YF["yfinance / FRED (macro)"]
    FG["Fear & Greed"]
    FND["funding agrégé"]
    LQ["liquidations"]
  end
  SOURCES --> MS["market_sources.py"]
  MS --> RC["runtime_cache.py (TTL + stale-while-error)\n+ cache_warmer.py"]

  subgraph PRIM["Primitives / indicateurs (analystes)"]
    IND["indicators (ema/rsi/atr/savitzky-golay/VP)"]
    PRO["pro_indicators (volume_profile, sizing)"]
    PAC["price_action (candlesticks, BOS/CHoCH, FVG, trap)"]
    RGF["regime_features (orderflow_entropy, up_fraction, slope→proba)"]
    BS["black_scholes (probas, expected move)"]
  end

  subgraph KB["Connaissance"]
    DRV["Drive package/ (trié)"] --> EXT["extraction/*.md (70 fiches)"]
    EXT --> KBP["knowledge_base.py"]
    KBP --> KJSON[("knowledge.json — LA BASE")]
    TRG[("drive_triage.json (registre de tri)")]
  end

  RC --> BRAIN
  PRIM --> BRAIN
  KJSON -. "rules_for()" .-> BRAIN

  subgraph BRAIN["Cerveau — swarm_brain.py (mixture of experts)"]
    AG["8 agents : orderflow · technicals · macro · sentiment · derivs · liquidations · divergent · structure"]
    AGG["aggregate → consensus / biais (zone morte)"]
    COG["cognition (entropie, accord, groupthink) + volatility_regime (CVIX)"]
    LRN["learn() → EARCP (perf + cohérence)"]
    AG --> AGG --> COG
    COG --> WGT[("brain_weights.json")]
    LRN --> WGT
  end

  BRAIN --> LOG[("brain_log.json")]
  LOG --> LRN

  COG --> DASH["Dashboard (lecture seule)\nTradingView charts + marqueur conscience\n+ bandes CVIX + aimants liquidation + multi-TF"]

  subgraph LAB["Recherche / Laboratoire"]
    BT["backtest_brain (evaluate / walk-forward / PBO)"]
    SL["strategy_lab.py (agent backtester AUTONOME)"]
    KJSON --> SL
    PRIM --> SL
    BT --> SL
    SL --> OUT[("strategies_out/ — rapport .md + code prêt à l'emploi .py")]
  end

  subgraph RISK["Risque (FIGÉ : config/env, jamais appris)"]
    RM["risk_manager (kill-switch, caps, perte journalière)"]
    RL["risk_limits (caps portefeuille)"]
    PS["position_sizer (stop ≥ k·ATR)"]
    RP["risk_profiles (agressivité 1..5, anti-martingale)"]
  end

  COG --> ORD["Pipeline d'ordres (paper / dry-run)\norder_signal_engine → preorder → execution_gateway"]
  RISK -- "OUI / NON" --> ORD

  SEC["security_agent + safe_push_check.sh"] -. "garde-fou code" .-> BRAIN
```

## Vue ASCII (terminal)

```
        ┌───────────── DÉPLOIEMENT ─────────────┐
        │ VPS(principal) · Termux(signaux)       │
        │ PC+Drive Desktop(G:) · MCP(analyse)    │
        └────────────────────────────────────────┘

 SOURCES (perception)                    CONNAISSANCE
 ┌──────────────────────────┐           ┌───────────────────────────┐
 │ Bitget · CoinGecko(repli) │           │ Drive package/ (trié)      │
 │ yfinance/FRED · Fear&Greed│           │   └─ extraction/*.md ──┐    │
 │ funding · liquidations    │           │ drive_triage.json      │    │
 └─────────────┬─────────────┘           │ knowledge_base.py ◄────┘    │
        market_sources.py                │   └─► knowledge.json (DB)   │
               ▼                          └─────────────┬──────────────┘
   ┌────────────────────────┐                           │ rules_for()
   │ runtime_cache (+warmer) │                          │
   └───────────┬────────────┘                           │
               ▼          primitives (analystes) ◄───────┘
        ╔═══════════════════════════════════════════════════════╗
        ║  CERVEAU  swarm_brain.py   (indicators, pro_indicators,║
        ║  price_action, regime_features, black_scholes)         ║
        ║  8 agents → aggregate → cognition+CVIX → conviction    ║
        ║  learn() → EARCP → brain_weights.json                  ║
        ║         (apprend les POIDS, jamais le RISQUE)          ║
        ╚════════╤═══════════════════════════╤══════════════════╝
                 │ advisory                   │ brain_log.json
                 ▼                            ▼
        DASHBOARD (lecture seule)      LABO  backtest_brain + strategy_lab
        charts + marqueur conscience   → strategies_out/ (rapport + code)
        bandes CVIX · aimants liq

 RISQUE (figé, config/env)                GARDE-FOUS CODE
 ┌──────────────────────────────────┐    ┌──────────────────────┐
 │ risk_manager (kill-switch, caps)  │    │ security_agent       │
 │ risk_limits · position_sizer      │    │ safe_push_check.sh   │
 │ risk_profiles (anti-martingale)   │    └──────────────────────┘
 └──────────────┬───────────────────┘
                │ OUI/NON
                ▼
   PIPELINE D'ORDRES (paper/dry-run) — AUCUN ordre réel par défaut
   order_signal_engine → preorder → execution_gateway
```

## Liaisons clés (qui parle à qui)

| De | Vers | Lien |
|---|---|---|
| Sources externes | `market_sources` → `runtime_cache` | données cachées (TTL + stale-while-error) |
| `runtime_cache` + primitives | **8 agents** (`swarm_brain`) | features de vote |
| `knowledge.json` | agents & `strategy_lab` | `kb.rules_for(...)` (règles extraites) |
| 8 agents | `aggregate` → `cognition`+CVIX | consensus, prudence, conviction ajustée |
| `brain_log.json` + prix | `learn()` → EARCP | mise à jour des **poids** (jamais le risque) |
| Cerveau | **Dashboard** | advisory (charts + marqueur conscience) |
| primitives + `backtest_brain` + KB | **`strategy_lab`** | fabrique/teste/classe/**promeut** → `strategies_out/` |
| Cerveau | **Risque** → pipeline d'ordres | OUI/NON avant tout (paper/dry-run) |

## Frontières de sécurité
- 🔒 **L'apprentissage (EARCP) ne touche QUE les poids** (`brain_weights.json`).
  Les **limites de risque** viennent de l'**env/config**, jamais apprises.
- 🔒 **Aucun ordre réel** par défaut : tout est advisory / paper / dry-run ; la
  couche risque doit dire OUI.
- 🔒 `security_agent` + `safe_push_check.sh` gardent le **code** (SAFE) avant push.

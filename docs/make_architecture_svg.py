"""
make_architecture_svg.py — génère docs/architecture.svg (diagramme infra, sans dépendance).

SAFE : écrit un fichier SVG. Lance :  python docs/make_architecture_svg.py
"""

from pathlib import Path

W, H = 1240, 1480
OUT = Path(__file__).resolve().parent / "architecture.svg"

PAL = {
    "deploy": ("#2b313c", "#3a4250"),
    "src": ("#16314f", "#2f6db0"),
    "cache": ("#0f3b3a", "#1f9b96"),
    "prim": ("#2e1f4a", "#8a5cf0"),
    "kb": ("#3a2f10", "#e0a52a"),
    "brain": ("#0f3320", "#2ec27e"),
    "dash": ("#152a3a", "#4ea1ff"),
    "lab": ("#3a230f", "#f0922a"),
    "risk": ("#3a1418", "#f5566b"),
    "order": ("#2a0f12", "#c0303d"),
    "guard": ("#1d2430", "#6b7686"),
}
parts = []


def _esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def box(x, y, w, h, kind, title, sub="", fs=14):
    bg, br = PAL[kind]
    title, sub = _esc(title), _esc(sub)
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" '
                 f'fill="{bg}" stroke="{br}" stroke-width="2"/>')
    parts.append(f'<text x="{x + w/2}" y="{y + (h/2 if not sub else h/2 - 7)}" '
                 f'fill="#e8edf2" font-size="{fs}" font-weight="600" '
                 f'text-anchor="middle" font-family="monospace">{title}</text>')
    if sub:
        parts.append(f'<text x="{x + w/2}" y="{y + h/2 + 13}" fill="#aab4c0" '
                     f'font-size="10.5" text-anchor="middle" font-family="monospace">{sub}</text>')


def cluster(x, y, w, h, kind, label):
    bg, br = PAL[kind]
    label = _esc(label)
    parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="none" '
                 f'stroke="{br}" stroke-width="1.4" stroke-dasharray="5 4" opacity="0.75"/>')
    parts.append(f'<text x="{x + 12}" y="{y + 20}" fill="{br}" font-size="13" '
                 f'font-weight="700" font-family="monospace">{label}</text>')


def arrow(x1, y1, x2, y2, color="#9fb0c0", dash=False, label="", w=2):
    d = ' stroke-dasharray="6 5"' if dash else ""
    parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" '
                 f'stroke-width="{w}"{d} marker-end="url(#ah)"/>')
    if label:
        parts.append(f'<text x="{(x1+x2)/2}" y="{(y1+y2)/2 - 5}" fill="#cdd6e0" '
                     f'font-size="10" text-anchor="middle" font-family="monospace">{_esc(label)}</text>')


# --- en-tête / marqueur de flèche ---
parts.append(f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
             f'viewBox="0 0 {W} {H}" font-family="monospace">')
parts.append('<defs><marker id="ah" markerWidth="10" markerHeight="10" refX="8" refY="3" '
             'orient="auto" markerUnits="strokeWidth">'
             '<path d="M0,0 L8,3 L0,6 z" fill="#9fb0c0"/></marker></defs>')
parts.append(f'<rect width="{W}" height="{H}" fill="#0b0e13"/>')
parts.append(f'<text x="{W/2}" y="30" fill="#e8edf2" font-size="20" font-weight="700" '
             f'text-anchor="middle">Écosystème — infrastructure &amp; connexions</text>')

# --- DÉPLOIEMENT (bandeau) ---
cluster(40, 46, W - 80, 52, "deploy", "DÉPLOIEMENT")
for i, (t, s) in enumerate([("VPS", "principal"), ("Termux", "signaux"),
                            ("PC + Drive Desktop", "G:\\"), ("MCP", "analyse")]):
    box(70 + i * 285, 60, 250, 30, "deploy", t, s, fs=12)

# --- SOURCES (gauche) + CONNAISSANCE (droite) ---
cluster(40, 120, 560, 150, "src", "SOURCES (perception)")
srcs = ["Bitget REST", "CoinGecko (repli)", "yfinance / FRED",
        "Fear & Greed", "funding agrégé", "liquidations"]
for i, t in enumerate(srcs):
    box(60 + (i % 3) * 180, 150 + (i // 3) * 52, 165, 40, "src", t, fs=11)

cluster(650, 120, 550, 230, "kb", "CONNAISSANCE")
box(680, 175, 220, 44, "kb", "Drive package/ (trié)", "tri + analyse (off-repo)")
box(940, 150, 230, 40, "kb", "knowledge_base.py", "build / query")
box(940, 215, 230, 46, "kb", "knowledge.json", "★ LA BASE (DB)")
box(680, 270, 490, 36, "kb", "agents & strategy_lab : kb.rules_for(...)", fs=11)
arrow(900, 197, 940, 180)
arrow(1055, 190, 1055, 215)

# --- market_sources + cache ---
box(160, 300, 220, 42, "cache", "market_sources.py", "Bitget→CoinGecko")
box(160, 372, 220, 46, "cache", "runtime_cache.py", "TTL + stale-while-error")
arrow(270, 270, 270, 300, label="")        # sources -> market_sources
arrow(270, 342, 270, 372)

# --- PRIMITIVES (droite) ---
cluster(650, 372, 550, 132, "prim", "PRIMITIVES / indicateurs (analystes)")
prims = ["indicators", "pro_indicators", "price_action",
         "regime_features", "black_scholes", "(VP, FVG, BOS…)"]
for i, t in enumerate(prims):
    box(670 + (i % 3) * 178, 402 + (i // 3) * 50, 165, 38, "prim", t, fs=11)

# --- CERVEAU ---
cluster(120, 470, 470, 250, "brain", "CERVEAU — swarm_brain.py (mixture of experts)")
box(140, 500, 430, 40, "brain", "8 agents", "orderflow·technicals·macro·sentiment·derivs·liq·divergent·structure", fs=12)
box(140, 552, 200, 44, "brain", "aggregate", "consensus / biais")
box(370, 552, 200, 44, "brain", "cognition + CVIX", "prudence")
box(140, 612, 200, 44, "brain", "learn() → EARCP", "perf + cohérence")
box(370, 612, 200, 44, "brain", "brain_weights.json", "POIDS appris")
box(140, 672, 430, 34, "brain", "→ conviction ajustée (advisory)", fs=12)
arrow(355, 540, 240, 552)
arrow(355, 540, 470, 552)
arrow(240, 596, 240, 612)
arrow(340, 634, 370, 634)
arrow(240, 656, 240, 672)
arrow(470, 596, 470, 612)

# liaisons entrantes vers le cerveau
arrow(270, 418, 270, 500, label="features")                 # cache -> brain
arrow(820, 504, 560, 520, dash=True)                        # primitives -> brain
arrow(1055, 256, 1055, 300)                                  # knowledge.json down
arrow(1055, 300, 590, 470, dash=True, label="rules_for()")  # KB -> brain

# --- brain_log boucle ---
box(370, 730, 200, 34, "brain", "brain_log.json", "journal", fs=11)
arrow(240, 706, 240, 745)
arrow(370, 747, 340, 706, dash=True, label="learn")

# --- DASHBOARD (bas gauche) ---
cluster(40, 800, 360, 150, "dash", "DASHBOARD (lecture seule)")
box(60, 832, 320, 44, "dash", "TradingView charts", "marqueur conscience")
box(60, 888, 320, 44, "dash", "bandes CVIX · aimants liq", "multi-timeframe")
arrow(200, 706, 200, 800, label="advisory")

# --- LABO (bas droite) ---
cluster(650, 540, 550, 210, "lab", "RECHERCHE / LABORATOIRE")
box(680, 572, 230, 44, "lab", "backtest_brain", "evaluate · WF · PBO")
box(940, 572, 230, 44, "lab", "strategy_lab.py", "agent AUTONOME")
box(680, 632, 490, 44, "lab", "stratégies pures/causales + compose + améliore", "(ema·rsi·donchian·VP·structure·ensembles)", fs=11)
box(680, 692, 490, 40, "lab", "strategies_out/", "★ rapport .md + code prêt à l'emploi .py")
arrow(910, 594, 940, 594)
arrow(820, 616, 820, 632)
arrow(925, 676, 925, 692)
arrow(820, 504, 820, 540, dash=True)                        # primitives -> lab
arrow(1100, 256, 1100, 540, dash=True, label="KB")          # KB -> lab

# --- RISQUE (bas) ---
cluster(120, 1000, 700, 150, "risk", "RISQUE (FIGÉ : config/env — jamais appris)")
box(140, 1032, 320, 44, "risk", "risk_manager", "kill-switch · caps · perte j.")
box(480, 1032, 320, 44, "risk", "risk_limits", "caps portefeuille")
box(140, 1090, 320, 44, "risk", "position_sizer", "stop ≥ k·ATR")
box(480, 1090, 320, 44, "risk", "risk_profiles", "agressivité · anti-martingale")
arrow(240, 706, 460, 1000, dash=True)                       # brain conviction -> risk (gate)

# --- GARDE-FOUS CODE ---
cluster(860, 1000, 340, 150, "guard", "GARDE-FOUS CODE")
box(880, 1032, 300, 44, "guard", "security_agent.py", "SAFE / RISKY")
box(880, 1090, 300, 44, "guard", "safe_push_check.sh", "avant push")

# --- PIPELINE D'ORDRES ---
box(120, 1200, 700, 56, "order", "PIPELINE D'ORDRES (paper / dry-run)",
    "order_signal_engine → preorder → execution_gateway   ·   AUCUN ordre réel par défaut", fs=13)
arrow(470, 1150, 470, 1200, label="OUI / NON")

# --- légende frontières de sécurité ---
parts.append(f'<text x="60" y="1310" fill="#2ec27e" font-size="12">🔒 Apprentissage = POIDS seulement (jamais le risque, figé en config/env)</text>')
parts.append(f'<text x="60" y="1332" fill="#f5566b" font-size="12">🔒 Aucun ordre réel par défaut — tout est advisory / paper / dry-run, la couche risque dit OUI</text>')
parts.append(f'<text x="60" y="1354" fill="#6b7686" font-size="12">🔒 security_agent + safe_push_check gardent le CODE avant chaque push</text>')
parts.append('<text x="60" y="1392" fill="#7f8a98" font-size="11">— flèche pleine = flux de données · flèche pointillée = consultation/contrôle —</text>')

parts.append('</svg>')
OUT.write_text("\n".join(parts), encoding="utf-8")
print(f"écrit : {OUT}  ({OUT.stat().st_size} octets)")

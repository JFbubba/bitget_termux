"""
neural_net.py — réseau neuronal de FUSION (méta-modèle) reliant tous les éléments
du cerveau, + carte de connectivité. PyTorch.

Classement : SAFE. Lecture seule, AUCUN ordre, aucun secret. Ce module NE passe
RIEN et NE touche PAS `guards()` : c'est un méta-modèle qui FUSIONNE non-linéairement
les votes des 14 agents (le banc GELÉ §62) en une prédiction directionnelle. Il est
consommé par `nn_agent.py` (16ᵉ voix opt-in, défaut OFF, poids fixe borné) et par le
dashboard (carte + prédiction). Les murs argent (50/250, ×5, stop, kill-switch, porte
d'edge) restent ABSOLUS et déterministes — rien ici ne les desserre.

Politique (contrainte « aucun réseau de neurones » LEVÉE le 06/07/2026) :
  • DÉTERMINISTE D'ABORD : le banc 14 reste le socle ; ce réseau est une SURCOUCHE.
  • BANC GELÉ INTACT : le méta-modèle LIT les votes des 14, il ne modifie JAMAIS
    leurs poids EARCP ni ne s'ajoute au banc — il est une 16ᵉ voix à part.
  • FAIL-SAFE : torch absent / poids absents / erreur -> prédiction neutre, jamais
    de crash. Entraînement OFFLINE (CLI), inférence rapide et cachée.

Architecture (§71) : ENSEMBLE de MLP [23 -> H -> H -> 1] ANTISYMÉTRIQUES
(logit = g(x) − g(x·flip) : renverser les signaux directionnels renverse la prédiction),
sigmoïdes moyennées. Entrée = 14 votes (`FEATURES`) + 9 contextuelles CAUSALES
(`EXTRA_FEATURES` : agrégats du banc, rendement/vol du symbole, heure UTC). Sortie =
P(rendement futur > 0) à l'horizon d'entraînement. Entraîné sur `brain_log_history.jsonl`
(journal profond ; repli `brain_log.json`), étiquette = signe du rendement forward
(deadband anti-bruit, split temporel purgé) ; l'edge HONNÊTE est mesuré en WALK-FORWARD
(moyenne sur K fenêtres) et c'est LUI que la 16e voix gate (muette si ≤ 0).
Poids sérialisés hors git (voir .gitignore).

CLI :
    python neural_net.py --train            # (ré)entraîne sur brain_log.json
    python neural_net.py --predict BTCUSDT  # prédiction live (nécessite des poids)
    python neural_net.py --map              # carte de connectivité (JSON)
"""
from __future__ import annotations

import json
import os
from pathlib import Path

# Ordre CANONIQUE des features = les 14 agents du banc gelé (swarm_brain.AGENTS).
# Figé : l'ordre définit la sémantique des poids sérialisés. Ne pas réordonner sans
# réentraîner (le méta-fichier porte un `feature_hash` qui refuse un modèle désaligné).
FEATURES = ["orderflow", "technicals", "macro", "sentiment", "derivs", "liquidations",
            "divergent", "structure", "simons", "savant", "geometric", "flows",
            "carry", "leadlag"]

# Features CONTEXTUELLES dérivées (§71) — STRICTEMENT CAUSALES (passé du même journal,
# jamais le futur), calculées à l'identique à l'entraînement et à l'inférence :
#   • agrégats du banc : moyenne, dispersion, accord de signe, delta de consensus 15 min ;
#   • dynamique du symbole : rendement 15/60 min et volatilité 60 min (échelles fixes) ;
#   • saisonnalité intra-jour : heure UTC en sin/cos.
EXTRA_FEATURES = ["consensus_mean", "consensus_disp", "sign_agree", "consensus_delta",
                  "ret_15m", "ret_60m", "vol_60m", "hour_sin", "hour_cos"]
# Partition pour l'ANTISYMÉTRIE : les features DIRECTIONNELLES changent de signe quand
# le marché « se retourne » (votes, rendements, deltas) ; le CONTEXTE (vol, dispersion,
# heure) est invariant. Le réseau antisymétrique garantit f(-dir, ctx) = -f(dir, ctx).
DIR_EXTRAS = {"consensus_mean", "sign_agree", "consensus_delta", "ret_15m", "ret_60m"}
IN_DIM = len(FEATURES) + len(EXTRA_FEATURES)
RET_SCALE = 0.005                 # 0.5 % -> 1.0 (rendements 15/60 min, clampés)
VOL_SCALE = 0.002                 # 0.2 %/pas -> 1.0 (volatilité 1 min, clampée)

REPO = Path(__file__).resolve().parent
WEIGHTS_PATH = REPO / "neural_net_weights.pt"
META_PATH = REPO / "neural_net_meta.json"
HISTORY_PATH = REPO / "brain_log_history.jsonl"   # journal PROFOND (jours) — source préférée
HIDDEN = 32                       # petit MLP : peu de données, on évite le surapprentissage
DROPOUT = 0.15                    # régularisation (le signal est faible, le bruit fort)
ARCH_V = 3                        # version d'architecture (garde au chargement : ≠ -> réentraîner)
ANTISYM = True                    # prior : renverser tous les signaux directionnels renverse la prédiction
N_ENS = 3                         # ensemble de graines (moyenne des sigmoïdes : moins de variance)
WF_FOLDS = 4                      # walk-forward : l'edge honnête = moyenne sur K fenêtres temporelles
HORIZON_S = int(os.getenv("NN_HORIZON_S", "") or 900)   # étiquette = rendement à ~15 min
DEADBAND = float(os.getenv("NN_DEADBAND", "") or 5e-4)  # |ret| < 5 bps -> étiquette bruit, ignorée
LABEL_TOL_S = 600                 # trou de données : étiquette au-delà de horizon+tol -> ignorée
PAST_WINDOW = 70                  # entrées de passé par échantillon (≈70 min : couvre le lookback 60 min)
SEED = 1729                       # déterminisme (repro des poids)


def feature_hash():
    """Empreinte de l'ordre des features (banc + contextuelles) : garde-fou contre
    un modèle désaligné avec le schéma d'entrée courant."""
    import hashlib
    return hashlib.sha1((",".join(FEATURES) + "|" + ",".join(EXTRA_FEATURES))
                        .encode()).hexdigest()[:12]


# --------------------------------------------------------------------------- #
#  Assemblage des features (câblage de tous les éléments) — PUR, sans torch   #
# --------------------------------------------------------------------------- #
def vector_from_votes(votes):
    """Vecteur de features [len(FEATURES)] à partir d'un dict de votes d'agents.

    `votes[name]` peut être un scalaire (format brain_log) ou un dict {vote, confidence}
    (format live). Agent manquant/illisible -> 0.0 (fail-safe, jamais d'exception).
    C'est le point où TOUS les éléments décisionnels convergent en une entrée unique."""
    out = []
    for name in FEATURES:
        v = (votes or {}).get(name, 0.0)
        try:
            if isinstance(v, dict):
                val = float(v.get("vote", 0.0) or 0.0) * float(v.get("confidence", 1.0) or 0.0)
            else:
                val = float(v)
        except (TypeError, ValueError):
            val = 0.0
        out.append(max(-1.0, min(1.0, val)))
    return out


def extras_from_seq(past, entry):
    """Features contextuelles CAUSALES pour `entry` (une ligne du journal du cerveau),
    à partir de `past` = entrées ANTÉRIEURES du MÊME symbole (triées par ts croissant).
    Utilisée à l'identique à l'entraînement (fenêtre du dataset) et à l'inférence
    (queue de brain_log.json). Fail-safe : composant illisible/absent -> 0.0.
    Renvoie [len(EXTRA_FEATURES)] dans l'ordre EXTRA_FEATURES, borné [-1, 1]."""
    import math
    votes_vec = vector_from_votes(entry.get("votes") or {})
    n = len(votes_vec)
    mean = sum(votes_vec) / n
    disp = (sum((v - mean) ** 2 for v in votes_vec) / n) ** 0.5
    agree = (sum(1 for v in votes_vec if v > 0) - sum(1 for v in votes_vec if v < 0)) / n
    ts = entry.get("ts") or 0
    price = entry.get("price") or 0

    def _at(delta_s):
        cible = ts - delta_s
        for e in reversed(past):
            if (e.get("ts") or 0) <= cible and e.get("price"):
                return e
        return None

    def _ret(delta_s):
        e = _at(delta_s)
        if not e or not price:
            return 0.0
        try:
            r = (price - e["price"]) / e["price"]
        except (ZeroDivisionError, TypeError):
            return 0.0
        return max(-1.0, min(1.0, r / RET_SCALE))

    r15, r60 = _ret(900), _ret(3600)
    # volatilité des rendements pas-à-pas sur ~60 min de passé (échelle fixe)
    vol = 0.0
    win = [e.get("price") for e in past if (e.get("ts") or 0) >= ts - 3600 and e.get("price")]
    if price:
        win.append(price)
    if len(win) >= 10:
        rets = [(b - a) / a for a, b in zip(win, win[1:]) if a]
        if len(rets) >= 5:
            m = sum(rets) / len(rets)
            sd = (sum((r - m) ** 2 for r in rets) / len(rets)) ** 0.5
            vol = max(0.0, min(1.0, sd / VOL_SCALE))
    cd = 0.0
    e15 = _at(900)
    try:
        if e15 is not None and entry.get("consensus") is not None and e15.get("consensus") is not None:
            cd = max(-1.0, min(1.0, float(entry["consensus"]) - float(e15["consensus"])))
    except (TypeError, ValueError):
        cd = 0.0
    h = ((ts % 86400) / 86400.0) * 2.0 * math.pi
    return [mean, disp, agree, cd, r15, r60, vol, math.sin(h), math.cos(h)]


def _recent_entries(symbol, max_n=PAST_WINDOW):
    """Queue du journal COURT (brain_log.json) pour un symbole, triée par ts —
    le passé récent qu'exige extras_from_seq à l'inférence. Fail-safe : []."""
    try:
        rows = json.loads((REPO / "brain_log.json").read_text(encoding="utf-8"))
        seq = sorted((e for e in rows if e.get("symbol") == str(symbol).upper()),
                     key=lambda e: e.get("ts", 0))
        return seq[-int(max_n):]
    except Exception:
        return []


def assemble_live(symbol, votes=None, now=None):
    """Assemble le vecteur LIVE complet (votes + contextuelles). Si `votes` est fourni
    (déjà calculé par le cerveau, cas de la 16ᵉ voix), on le RÉUTILISE — pas de recalcul,
    pas de récursion. Sinon, on interroge le cerveau en lecture (peek) de façon défensive.
    Les contextuelles viennent de la queue de brain_log.json (fail-safe : zéros)."""
    if votes is None:
        try:
            import swarm_brain
            res = swarm_brain.peek(symbol)
            votes = {c["agent"]: c["vote"] for c in (res.get("agents") or [])}
        except Exception:
            votes = {}
    seq = _recent_entries(symbol)
    import time as _t
    now = _t.time() if now is None else now
    last = seq[-1] if seq else {}
    entry = {"ts": int(now), "price": last.get("price"),
             "votes": votes, "consensus": last.get("consensus")}
    return vector_from_votes(votes) + extras_from_seq(seq, entry)


# --------------------------------------------------------------------------- #
#  Réseau (torch, importé PARESSEUSEMENT)                                      #
# --------------------------------------------------------------------------- #
def _flip_vector(in_dim):
    """Vecteur de retournement : -1 sur les features DIRECTIONNELLES (votes, rendements,
    deltas), +1 sur le CONTEXTE (vol, dispersion, heure). PUR."""
    out = []
    for i in range(in_dim):
        if i < len(FEATURES):
            out.append(-1.0)                          # les 14 votes sont directionnels
        elif i - len(FEATURES) < len(EXTRA_FEATURES):
            out.append(-1.0 if EXTRA_FEATURES[i - len(FEATURES)] in DIR_EXTRAS else 1.0)
        else:
            out.append(1.0)
    return out


def _build_net(torch, nn, in_dim, hidden=None, antisym=None):
    """MLP de fusion. Si `antisym`, le logit est g(x) − g(x·flip) : renverser tous les
    signaux directionnels renverse EXACTEMENT la prédiction (f(-d,c) = -f(d,c)) — un
    prior de symétrie du marché qui divise l'espace à apprendre par deux."""
    hidden = HIDDEN if hidden is None else int(hidden)
    antisym = ANTISYM if antisym is None else bool(antisym)

    class FusionNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.g = nn.Sequential(
                nn.Linear(in_dim, hidden), nn.ReLU(), nn.Dropout(DROPOUT),
                nn.Linear(hidden, hidden), nn.ReLU(), nn.Dropout(DROPOUT),
                nn.Linear(hidden, 1),
            )
            self.antisym = antisym
            self.register_buffer("flip", torch.tensor(_flip_vector(in_dim),
                                                      dtype=torch.float32))

        def forward(self, x):
            if not self.antisym:
                return self.g(x)             # logit brut (sigmoïde appliquée hors du modèle)
            return self.g(x) - self.g(x * self.flip)

    return FusionNet()


_CACHE = {"model": None, "meta": None, "loaded": False}


def edge_bound(meta, prudent=True):
    """Edge hors-échantillon d'après la méta du dernier entraînement. `prudent` (défaut) :
    borne wf_edge − erreur-type inter-plis (un edge moyen minuscule sur des plis à ±0.08
    est du bruit, §71) ; sinon la moyenne walk-forward brute. Repli : val_acc − taux de
    base. None si indisponible. PUR."""
    try:
        if meta.get("wf_edge") is not None:
            e = float(meta["wf_edge"])
            if prudent:
                e -= float(meta.get("wf_edge_se") or 0.0)
            return round(e, 4)
        return round(float(meta["val_acc"]) - float(meta["val_base_rate"]), 4)
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def _notify_gate_transition(old_meta, new_meta):
    """Alerte Telegram (best-effort, jamais d'exception) quand la PORTE D'EDGE de la
    16e voix change d'état après un réentraînement : le propriétaire apprend LE JOUR
    où la voix commence à parler (ou se tait de nouveau) sans surveiller les métas.
    Suit le CRITÈRE CONFIGURÉ (NN_EDGE_GATE prudent/brut) — l'alerte annonce l'état
    de la porte qui gouverne RÉELLEMENT la voix."""
    try:
        mode = "prudent"
        try:
            import nn_agent
            mode = nn_agent._gate_mode()
        except Exception:
            pass
        prudent = mode != "brut"
        avant = edge_bound(old_meta or {}, prudent=prudent)
        apres = edge_bound(new_meta or {}, prudent=prudent)
        if avant is None or apres is None:
            return
        ouvre = avant <= 0.0 < apres
        ferme = apres <= 0.0 < avant
        if not (ouvre or ferme):
            return
        import telegram_notifier as tn
        if ouvre:
            tn.send_telegram(f"🧠 16e voix (NN) : edge {mode} PASSÉ POSITIF ({apres:+.3f}) — "
                             "si NN_AGENT_ENABLED=1 elle PARLE désormais dans le consensus "
                             "(confiance plafonnée, murs argent intacts).")
        else:
            tn.send_telegram(f"🧠 16e voix (NN) : edge {mode} repassé ≤ 0 ({apres:+.3f}) — "
                             "elle se TAIT de nouveau (porte d'edge).")
    except Exception:
        pass


def _load_model():
    """Charge l'ENSEMBLE entraîné (caché) : liste de modèles dont les sigmoïdes sont
    moyennées à l'inférence. None si torch/poids absents ou schéma/architecture
    désalignés (fail-safe : on préfère « pas de prédiction » à une prédiction fausse)."""
    if _CACHE["loaded"]:
        return _CACHE["model"], _CACHE["meta"]
    _CACHE["loaded"] = True
    try:
        import torch
        from torch import nn
    except Exception:
        return None, None
    if not WEIGHTS_PATH.exists() or not META_PATH.exists():
        return None, None
    try:
        meta = json.loads(META_PATH.read_text(encoding="utf-8"))
        if meta.get("feature_hash") != feature_hash():
            return None, None                # schéma d'entrée désaligné
        if int(meta.get("arch_v", 0)) != ARCH_V:
            return None, None                # architecture désalignée -> réentraîner
        payload = torch.load(WEIGHTS_PATH, map_location="cpu")
        states = payload["models"] if isinstance(payload, dict) and "models" in payload else [payload]
        models = []
        for sd in states:
            m = _build_net(torch, nn, int(meta.get("in_dim", IN_DIM)),
                           hidden=meta.get("hidden"), antisym=meta.get("antisym"))
            m.load_state_dict(sd)
            m.eval()
            models.append(m)
        _CACHE["model"], _CACHE["meta"] = models, meta
        return models, meta
    except Exception:
        return None, None


def predict(symbol="BTCUSDT", votes=None):
    """Prédiction de fusion. Renvoie {p_up, vote, confidence, note} OU None si le
    modèle est indisponible (fail-safe total : torch absent, pas de poids, erreur).

    - p_up      : P(rendement futur > 0) ∈ [0,1]
    - vote      : (p_up-0.5)*2 ∈ [-1,1], directionnel
    - confidence: |p_up-0.5|*2 ∈ [0,1], conviction du réseau
    """
    models, meta = _load_model()
    if not models:
        return None
    try:
        import torch
        x = torch.tensor([assemble_live(symbol, votes)], dtype=torch.float32)
        with torch.no_grad():
            ps = [float(torch.sigmoid(m(x)).item()) for m in models]
        p = sum(ps) / len(ps)                # moyenne d'ensemble (moins de variance)
        vote = max(-1.0, min(1.0, (p - 0.5) * 2.0))
        conf = abs(p - 0.5) * 2.0
        # edge hors-échantillon, DEUX lectures exposées pour la porte de la 16e voix :
        # val_edge = borne PRUDENTE (wf_edge − erreur-type inter-plis, défaut du gate) ;
        # val_edge_brut = moyenne walk-forward seule (gate NN_EDGE_GATE=brut).
        val_edge = edge_bound(meta, prudent=True)
        val_edge_brut = edge_bound(meta, prudent=False)
        return {"p_up": round(p, 4), "vote": round(vote, 4),
                "confidence": round(conf, 4), "val_edge": val_edge,
                "val_edge_brut": val_edge_brut,
                "note": f"nn v{meta.get('version', '?')}"}
    except Exception:
        return None


# --------------------------------------------------------------------------- #
#  Entraînement OFFLINE (CLI) — sur brain_log.json                            #
# --------------------------------------------------------------------------- #
def _read_log(log_path=None):
    """Lit le journal du cerveau. Sans chemin explicite : préfère l'HISTORIQUE JSONL
    (profondeur de plusieurs jours, cible du timer bitget-neural-train) au journal
    court brain_log.json. Une ligne JSONL corrompue est ignorée (fail-safe)."""
    if log_path is None:
        log_path = HISTORY_PATH if HISTORY_PATH.exists() else (REPO / "brain_log.json")
    p = Path(log_path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".jsonl":
        rows = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
        return rows
    return json.loads(text)


def _dataset(log_path=None, with_ts=False):
    """Construit (X, y) depuis le journal du cerveau : pour chaque entrée (symbol, ts,
    price, votes), l'étiquette est le SIGNE du rendement à HORIZON_S (première entrée
    du même symbole à ts+HORIZON_S). Hygiène des étiquettes :
      • deadband — |rendement| < DEADBAND (micro-variation) = bruit, échantillon ignoré ;
      • tolérance — étiquette trouvée au-delà de HORIZON_S+LABEL_TOL_S (trou de données,
        bot à l'arrêt) = mauvais horizon, échantillon ignoré.
    Les échantillons sont TRIÉS PAR TEMPS GLOBAL (tous symboles confondus) pour que le
    split de validation de train() soit réellement temporel (le passé prédit le futur,
    pas de fuite transversale entre symboles corrélés). Renvoie (X, y) ou (X, y, ts)."""
    rows = _read_log(log_path)
    by_sym = {}
    for e in rows:
        by_sym.setdefault(e.get("symbol"), []).append(e)
    samples = []
    for sym, seq in by_sym.items():
        seq = sorted(seq, key=lambda e: e.get("ts", 0))
        j = 0                                # deux pointeurs : la cible avance avec i
        for i, e in enumerate(seq):
            price = e.get("price")
            if not price:
                continue
            target_ts = e.get("ts", 0) + HORIZON_S
            j = max(j, i + 1)
            while j < len(seq) and (seq[j].get("ts", 0) < target_ts or not seq[j].get("price")):
                j += 1
            if j >= len(seq):
                break
            fut = seq[j]
            if fut.get("ts", 0) - target_ts > LABEL_TOL_S:
                continue
            ret = (fut["price"] - price) / price
            if abs(ret) < DEADBAND:
                continue
            past = seq[max(0, i - PAST_WINDOW):i]     # fenêtre CAUSALE bornée (jamais le futur)
            samples.append((e.get("ts", 0),
                            vector_from_votes(e.get("votes") or {}) + extras_from_seq(past, e),
                            1 if ret > 0 else 0))
    samples.sort(key=lambda s: s[0])
    X = [s[1] for s in samples]
    y = [s[2] for s in samples]
    if with_ts:
        return X, y, [s[0] for s in samples]
    return X, y


def _fit(torch, tnn, Xtr_t, ytr_t, Xva_t, yva_t, seed, epochs, lr, batch_size, patience,
         hidden=None, antisym=None, pos_weight=None):
    """Entraîne UN réseau (mini-batches, early-stopping sur la perte de validation).
    Déterministe par graine (init + shuffle). Renvoie (model, best_val_loss)."""
    torch.manual_seed(seed)
    model = _build_net(torch, tnn, Xtr_t.shape[1], hidden=hidden, antisym=antisym)
    loss_fn = tnn.BCEWithLogitsLoss(pos_weight=pos_weight)
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    gen = torch.Generator().manual_seed(seed)
    best_val, best_state, since_best = 1e9, None, 0
    for _ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xtr_t), generator=gen)
        for k in range(0, len(perm), batch_size):
            idx = perm[k:k + batch_size]
            opt.zero_grad()
            loss = loss_fn(model(Xtr_t[idx]), ytr_t[idx])
            loss.backward()
            opt.step()
        model.eval()
        with torch.no_grad():
            vloss = float(loss_fn(model(Xva_t), yva_t).item())
        if vloss < best_val - 1e-5:
            best_val = vloss
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            since_best = 0
        else:
            since_best += 1
            if since_best >= patience:               # le val ne progresse plus
                break
    model.load_state_dict(best_state)
    model.eval()
    return model, best_val


def _purged_train_idx(ts, val_lo):
    """Indices de train STRICTEMENT antérieurs à la fenêtre de validation, PURGÉS :
    un exemple dont la fenêtre d'étiquette [ts, ts+HORIZON_S] mord sur la validation
    verrait le futur de celle-ci (anti-fuite). PUR."""
    val_start_ts = ts[val_lo]
    return [i for i in range(val_lo) if ts[i] + HORIZON_S <= val_start_ts]


def _pos_weight(torch, y_idx, y):
    """pos_weight : rééquilibre hausses/baisses de la fenêtre de train. PUR."""
    pos = sum(y[i] for i in y_idx) or 1
    neg = len(y_idx) - pos or 1
    return torch.tensor([neg / pos], dtype=torch.float32)


def walk_forward(X, y, ts, folds=WF_FOLDS, seed=SEED, epochs=200, lr=1e-3,
                 batch_size=256, patience=30, hidden=None, antisym=None, verbose=False):
    """Edge HONNÊTE : K fenêtres de validation temporelles consécutives, chacune prédite
    par un modèle entraîné sur son seul passé (fenêtre extensible, purge anti-fuite).
    Un split unique dépend du hasard de SA fenêtre (taux de base mesurés 0.57-0.71 §70) ;
    la moyenne des K (acc − base) est l'estimateur que la 16e voix gate. Renvoie
    {folds, wf_edge, wf_acc, wf_base, wf_brier} (wf_edge=None si données insuffisantes)."""
    import torch
    from torch import nn as tnn
    n = len(X)
    block = n // (folds + 1)
    if block < 50:
        return {"folds": [], "wf_edge": None, "note": f"trop peu d'exemples ({n})"}
    out = []
    for f in range(folds):
        lo = (f + 1) * block
        hi = (f + 2) * block if f < folds - 1 else n
        tr_idx = _purged_train_idx(ts, lo)
        if len(tr_idx) < 100 or hi - lo < 50:
            continue
        Xtr_t = torch.tensor([X[i] for i in tr_idx], dtype=torch.float32)
        ytr_t = torch.tensor([y[i] for i in tr_idx], dtype=torch.float32).unsqueeze(1)
        Xva_t = torch.tensor(X[lo:hi], dtype=torch.float32)
        yva_t = torch.tensor(y[lo:hi], dtype=torch.float32).unsqueeze(1)
        model, _ = _fit(torch, tnn, Xtr_t, ytr_t, Xva_t, yva_t, seed + f, epochs, lr,
                        batch_size, patience, hidden, antisym,
                        pos_weight=_pos_weight(torch, tr_idx, y))
        with torch.no_grad():
            p = torch.sigmoid(model(Xva_t))
            acc = float(((p > 0.5).float() == yva_t).float().mean().item())
            brier = float(((p - yva_t) ** 2).mean().item())
        up = float(yva_t.mean().item())
        base = max(up, 1.0 - up)
        out.append({"fold": f, "n_train": len(tr_idx), "n_val": hi - lo,
                    "acc": round(acc, 4), "base": round(base, 4),
                    "edge": round(acc - base, 4), "brier": round(brier, 4)})
        if verbose:
            print(f"  pli {f}: acc {acc:.3f} vs base {base:.3f} "
                  f"(edge {acc - base:+.3f} · brier {brier:.4f} · train {len(tr_idx)})")
    if not out:
        return {"folds": [], "wf_edge": None, "note": "plis insuffisants"}
    edges = [o["edge"] for o in out]
    mean_edge = sum(edges) / len(edges)
    # erreur-type de l'edge entre plis : la variance inter-fenêtres est GRANDE (±0.08
    # mesuré §71) — un edge moyen minuscule est du bruit ; la 16e voix gate la borne
    # prudente (edge − se), pas la moyenne brute.
    var = sum((e - mean_edge) ** 2 for e in edges) / len(edges)
    se = (var ** 0.5) / (len(edges) ** 0.5)
    return {"folds": out,
            "wf_edge": round(mean_edge, 4), "wf_edge_se": round(se, 4),
            "wf_acc": round(sum(o["acc"] for o in out) / len(out), 4),
            "wf_base": round(sum(o["base"] for o in out) / len(out), 4),
            "wf_brier": round(sum(o["brier"] for o in out) / len(out), 4)}


def train(log_path=None, epochs=300, lr=1e-3, val_frac=0.2, batch_size=256,
          patience=60, hidden=None, antisym=None, n_ens=None, wf=True, verbose=True):
    """Entraîne l'ENSEMBLE de fusion et sérialise poids + méta. Retourne les métriques.
    Déterministe (graines fixes). Nécessite torch (lève sinon — commande explicite).
    Deux temps : 1) walk-forward (edge honnête moyenné sur K fenêtres — c'est LUI que
    la 16e voix gate) ; 2) entraînement final : split temporel purgé (derniers val_frac)
    et N_ENS réseaux de graines différentes dont les sigmoïdes sont moyennées."""
    import torch
    from torch import nn as tnn

    X, y, ts = _dataset(log_path, with_ts=True)
    n = len(X)
    if n < 40:
        raise RuntimeError(f"trop peu d'exemples pour entraîner ({n}) — laisse tourner le cerveau")
    n_ens = N_ENS if n_ens is None else max(1, int(n_ens))

    # 1) edge honnête (walk-forward) — AVANT l'entraînement final
    if wf:
        if verbose:
            print(f"Walk-forward ({WF_FOLDS} plis) :")
        wf_stats = walk_forward(X, y, ts, epochs=min(epochs, 200), lr=lr,
                                batch_size=batch_size, patience=min(patience, 30),
                                hidden=hidden, antisym=antisym, verbose=verbose)
    else:
        wf_stats = {"folds": [], "wf_edge": None, "note": "désactivé"}

    # 2) split final purgé + ensemble
    n_val = max(4, int(n * val_frac))
    tr_idx = _purged_train_idx(ts, n - n_val)
    if len(tr_idx) < 20:
        raise RuntimeError(f"trop peu d'exemples de train après purge ({len(tr_idx)})")
    Xtr_t = torch.tensor([X[i] for i in tr_idx], dtype=torch.float32)
    ytr_t = torch.tensor([y[i] for i in tr_idx], dtype=torch.float32).unsqueeze(1)
    Xva_t = torch.tensor(X[n - n_val:], dtype=torch.float32)
    yva_t = torch.tensor(y[n - n_val:], dtype=torch.float32).unsqueeze(1)
    pw = _pos_weight(torch, tr_idx, y)

    models, val_losses = [], []
    for k in range(n_ens):
        model, best_val = _fit(torch, tnn, Xtr_t, ytr_t, Xva_t, yva_t, SEED + k, epochs,
                               lr, batch_size, patience, hidden, antisym, pos_weight=pw)
        models.append(model)
        val_losses.append(best_val)
        if verbose:
            print(f"membre {k}: val_loss {best_val:.4f}")

    with torch.no_grad():
        p_va = sum(torch.sigmoid(m(Xva_t)) for m in models) / len(models)
        p_tr = sum(torch.sigmoid(m(Xtr_t)) for m in models) / len(models)
        va_pred = (p_va > 0.5).float()
        val_acc = float((va_pred == yva_t).float().mean().item())
        tr_acc = float(((p_tr > 0.5).float() == ytr_t).float().mean().item())
        brier = float(((p_va - yva_t) ** 2).mean().item())
        # précision quand le réseau a de la CONVICTION (|p-0.5| >= 0.10) : c'est la
        # zone où la 16e voix pèse ; c'est elle qu'il faut surveiller, pas l'accuracy brute
        hi_mask = (p_va - 0.5).abs() >= 0.10
        hi_n = int(hi_mask.sum().item())
        hi_acc = float((va_pred[hi_mask] == yva_t[hi_mask]).float().mean().item()) if hi_n else None
    yva = y[n - n_val:]
    up_rate = sum(yva) / len(yva)
    base_rate = round(max(up_rate, 1 - up_rate), 4)   # accuracy du prédicteur constant (repère)

    torch.save({"models": [m.state_dict() for m in models]}, WEIGHTS_PATH)
    try:
        old_meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    except Exception:
        old_meta = {}
    version = int(old_meta.get("version", 0) or 0) + 1
    import datetime as _dt
    meta = {"version": version, "feature_hash": feature_hash(), "features": FEATURES,
            "extra_features": EXTRA_FEATURES, "in_dim": IN_DIM, "arch_v": ARCH_V,
            "hidden": HIDDEN if hidden is None else int(hidden), "dropout": DROPOUT,
            "antisym": ANTISYM if antisym is None else bool(antisym), "n_models": n_ens,
            "horizon_s": HORIZON_S, "deadband": DEADBAND,
            "source": str((Path(log_path) if log_path else
                           (HISTORY_PATH if HISTORY_PATH.exists() else REPO / "brain_log.json")).name),
            "n_samples": n, "n_train": len(tr_idx), "n_val": n_val,
            "data_from": _dt.datetime.fromtimestamp(ts[0], _dt.timezone.utc).isoformat(timespec="seconds"),
            "data_to": _dt.datetime.fromtimestamp(ts[-1], _dt.timezone.utc).isoformat(timespec="seconds"),
            "train_acc": round(tr_acc, 4), "val_acc": round(val_acc, 4),
            "val_base_rate": base_rate, "val_brier": round(brier, 4),
            "val_hiconf_acc": round(hi_acc, 4) if hi_acc is not None else None,
            "val_hiconf_n": hi_n,
            "val_loss": round(sum(val_losses) / len(val_losses), 4),
            "wf_edge": wf_stats.get("wf_edge"), "wf_edge_se": wf_stats.get("wf_edge_se"),
            "wf": wf_stats, "seed": SEED,
            "trained_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _CACHE["loaded"] = False                          # force le rechargement au prochain predict
    _notify_gate_transition(old_meta, meta)           # le propriétaire sait quand la voix s'ouvre
    if verbose:
        print(f"\nEntraîné (ensemble ×{n_ens}) sur {len(tr_idx)} exemples "
              f"(val {n_val}, purge {n - n_val - len(tr_idx)}) — "
              f"{sum(y)} hausses / {n - sum(y)} baisses.")
        print(f"Split final — train {tr_acc:.3f} · val {val_acc:.3f} (base {base_rate:.3f}) · "
              f"Brier {brier:.4f} · haute-conf {hi_acc if hi_acc is None else round(hi_acc, 3)} sur {hi_n}")
        print(f"Walk-forward — edge {wf_stats.get('wf_edge')} "
              f"(acc {wf_stats.get('wf_acc')} vs base {wf_stats.get('wf_base')}) "
              f"sur {len(wf_stats.get('folds') or [])} plis — C'EST L'EDGE QUE GATE LA 16e VOIX")
        print(f"Poids -> {WEIGHTS_PATH.name} · méta -> {META_PATH.name} (v{version})")
    return meta


# --------------------------------------------------------------------------- #
#  Carte de connectivité (le « réseau entre tous les éléments ») — PUR        #
# --------------------------------------------------------------------------- #
# Groupes d'ENTRÉE : au-delà des 14 agents entraînés, la carte montre les surcouches
# d'observation qui alimentent aussi le contexte du cerveau (SMC §64, LLM §06/07, etc.).
_INPUT_GROUPS = {
    "flux": ["orderflow", "liquidations", "flows", "derivs"],
    "prix/structure": ["technicals", "structure", "geometric", "divergent"],
    "quant": ["simons", "savant", "leadlag", "carry"],
    "contexte": ["macro", "sentiment"],
}
_OVERLAYS = ["smc", "llm"]                            # surcouches opt-in (observation)


def connectivity_map(symbol="BTCUSDT", votes=None, prediction=None, brain=None, smc=None):
    """Carte de connectivité pour le dashboard : nœuds (éléments) + arêtes (flux de
    données) + activation LIVE. Décrit littéralement le réseau reliant tous les éléments,
    de l'entrée (agents/surcouches) vers le cerveau, la fusion NN, puis les murs et
    l'exécution. LECTURE SEULE, best-effort (jamais d'exception vers l'appelant).

    `smc` (l'analyse SMC déjà calculée par le dashboard) est réutilisée si fournie —
    évite un second fetch de bougies. Passer smc={} désactive la surcouche SMC (tests)."""
    # récupère les votes live si non fournis
    if votes is None or brain is None:
        try:
            import swarm_brain
            b = brain or swarm_brain.peek(symbol)
            brain = b
            if votes is None:
                votes = {c["agent"]: c["vote"] for c in (b.get("agents") or [])}
        except Exception:
            votes, brain = votes or {}, brain or {}
    votes = votes or {}
    if prediction is None:
        prediction = predict(symbol, votes)

    nodes, edges = [], []

    def add(nid, label, group, act=None, meta=None):
        nodes.append({"id": nid, "label": label, "group": group,
                      "activation": None if act is None else round(float(act), 3),
                      **(meta or {})})

    # 1) nœuds d'entrée : les 14 agents (activation = vote live)
    for grp, names in _INPUT_GROUPS.items():
        for name in names:
            v = votes.get(name, 0.0)
            act = v.get("vote") if isinstance(v, dict) else v
            add(name, name, grp, act)
            edges.append({"from": name, "to": "brain"})
    # 2) surcouches d'observation (SMC, LLM) — présentes si actives
    smc_act = None
    try:
        a = smc                                       # réutilise l'analyse SMC du dashboard si fournie
        if a is None:                                 # sinon, calcul autonome (CLI) — best-effort
            import smc as _smc
            import market_sources as ms
            cs = ms.candles(symbol, "15m", 120)
            a = _smc.analyze(cs) if cs else {}
        if a and a.get("ok"):
            smc_act = (a.get("score", 0) / 4.0) * (1 if a.get("bias") == "LONG" else -1 if a.get("bias") == "SHORT" else 0)
    except Exception:
        pass
    add("smc", "SMC §64", "surcouche", smc_act, {"overlay": True})
    edges.append({"from": "smc", "to": "brain"})
    llm_on = False
    try:
        import llm_agent
        llm_on = llm_agent.enabled()
    except Exception:
        pass
    add("llm", "LLM 15e", "surcouche", votes.get("llm", {}).get("vote") if isinstance(votes.get("llm"), dict) else None,
        {"overlay": True, "enabled": llm_on})
    edges.append({"from": "llm", "to": "brain"})

    # 3) le cerveau (consensus des 14) -> le réseau de fusion NN (16e voix)
    add("brain", "Cerveau 14 (EARCP)", "coeur", (brain or {}).get("consensus"))
    edges.append({"from": "brain", "to": "nn"})
    nn_on = False
    try:
        import nn_agent
        nn_on = nn_agent.enabled()
    except Exception:
        pass
    add("nn", "Réseau de fusion", "coeur",
        (prediction or {}).get("vote"),
        {"p_up": (prediction or {}).get("p_up"), "enabled": nn_on,
         "trained": prediction is not None})
    edges.append({"from": "nn", "to": "consensus"})
    edges.append({"from": "brain", "to": "consensus"})

    # 4) consensus final -> MURS ABSOLUS -> exécution (déterministe, hors influence NN)
    add("consensus", "Consensus", "coeur", (brain or {}).get("consensus"))
    edges.append({"from": "consensus", "to": "guards"})
    add("guards", "Murs argent (guards)", "mur", None, {"absolute": True})
    edges.append({"from": "guards", "to": "exec"})
    add("exec", "Exécution bornée", "sortie", None)

    return {"symbol": symbol, "nodes": nodes, "edges": edges,
            "prediction": prediction, "nn_enabled": nn_on,
            "consensus": (brain or {}).get("consensus"),
            "meta": _CACHE.get("meta") or (_load_model()[1] or {})}


# --------------------------------------------------------------------------- #
#  CLI                                                                         #
# --------------------------------------------------------------------------- #
def main():
    import sys
    try:
        # comme brain_cycle : le cron/CLI n'a pas d'EnvironmentFile — sans ceci les
        # leviers env (NN_EDGE_GATE, NN_HORIZON_S…) seraient invisibles hors service.
        from dotenv import load_dotenv
        load_dotenv()
    except Exception:
        pass
    args = sys.argv[1:]
    if "--train" in args:
        i = args.index("--train")
        epochs = int(args[i + 1]) if i + 1 < len(args) and args[i + 1].isdigit() else 300
        train(epochs=epochs)
    elif "--predict" in args:
        i = args.index("--predict")
        sym = args[i + 1].upper() if i + 1 < len(args) else "BTCUSDT"
        p = predict(sym)
        print(json.dumps(p, indent=2, ensure_ascii=False) if p else
              "prédiction indisponible (torch/poids absents — lance --train)")
    elif "--map" in args:
        i = args.index("--map")
        sym = args[i + 1].upper() if i + 1 < len(args) and not args[i + 1].startswith("-") else "BTCUSDT"
        print(json.dumps(connectivity_map(sym), indent=2, ensure_ascii=False))
    else:
        print(__doc__.strip().splitlines()[-3])
        print("Usage : python neural_net.py [--train [epochs] | --predict SYMBOL | --map SYMBOL]")


if __name__ == "__main__":
    main()

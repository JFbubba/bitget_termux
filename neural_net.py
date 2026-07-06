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

Architecture : MLP [14 -> H -> H -> 1] (sigmoïde, dropout). Entrée = les 14 votes des
agents dans l'ordre `FEATURES`. Sortie = P(rendement futur > 0) à l'horizon d'entraînement.
Entraîné sur `brain_log_history.jsonl` (journal profond ; repli `brain_log.json`) avec
étiquette = signe du rendement forward (deadband anti-bruit, split temporel purgé).
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

REPO = Path(__file__).resolve().parent
WEIGHTS_PATH = REPO / "neural_net_weights.pt"
META_PATH = REPO / "neural_net_meta.json"
HISTORY_PATH = REPO / "brain_log_history.jsonl"   # journal PROFOND (jours) — source préférée
HIDDEN = 24                       # petit MLP : peu de données, on évite le surapprentissage
DROPOUT = 0.15                    # régularisation (le signal est faible, le bruit fort)
ARCH = f"mlp-{HIDDEN}x2-do{DROPOUT}"              # empreinte d'architecture (garde au chargement)
HORIZON_S = int(os.getenv("NN_HORIZON_S", "") or 900)   # étiquette = rendement à ~15 min
DEADBAND = float(os.getenv("NN_DEADBAND", "") or 5e-4)  # |ret| < 5 bps -> étiquette bruit, ignorée
LABEL_TOL_S = 600                 # trou de données : étiquette au-delà de horizon+tol -> ignorée
SEED = 1729                       # déterminisme (repro des poids)


def feature_hash():
    """Empreinte de l'ordre des features : garde-fou contre un modèle désaligné."""
    import hashlib
    return hashlib.sha1(",".join(FEATURES).encode()).hexdigest()[:12]


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


def assemble_live(symbol, votes=None):
    """Assemble le vecteur LIVE. Si `votes` est fourni (déjà calculé par le cerveau,
    cas de la 16ᵉ voix), on le RÉUTILISE — pas de recalcul, pas de récursion. Sinon,
    on interroge le cerveau en lecture (peek) de façon défensive."""
    if votes is None:
        try:
            import swarm_brain
            res = swarm_brain.peek(symbol)
            votes = {c["agent"]: c["vote"] for c in (res.get("agents") or [])}
        except Exception:
            votes = {}
    return vector_from_votes(votes)


# --------------------------------------------------------------------------- #
#  Réseau (torch, importé PARESSEUSEMENT)                                      #
# --------------------------------------------------------------------------- #
def _build_net(torch, nn, in_dim):
    class FusionNet(nn.Module):
        def __init__(self):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(in_dim, HIDDEN), nn.ReLU(), nn.Dropout(DROPOUT),
                nn.Linear(HIDDEN, HIDDEN), nn.ReLU(), nn.Dropout(DROPOUT),
                nn.Linear(HIDDEN, 1),
            )

        def forward(self, x):
            return self.net(x)               # logit brut (sigmoïde appliquée hors du modèle)

    return FusionNet()


_CACHE = {"model": None, "meta": None, "loaded": False}


def _load_model():
    """Charge le modèle entraîné (caché). None si torch/poids absents (fail-safe)."""
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
            return None, None                # modèle désaligné avec le schéma courant
        if meta.get("arch") != ARCH:
            return None, None                # architecture désalignée -> réentraîner (fail-safe)
        model = _build_net(torch, nn, len(FEATURES))
        model.load_state_dict(torch.load(WEIGHTS_PATH, map_location="cpu"))
        model.eval()
        _CACHE["model"], _CACHE["meta"] = model, meta
        return model, meta
    except Exception:
        return None, None


def predict(symbol="BTCUSDT", votes=None):
    """Prédiction de fusion. Renvoie {p_up, vote, confidence, note} OU None si le
    modèle est indisponible (fail-safe total : torch absent, pas de poids, erreur).

    - p_up      : P(rendement futur > 0) ∈ [0,1]
    - vote      : (p_up-0.5)*2 ∈ [-1,1], directionnel
    - confidence: |p_up-0.5|*2 ∈ [0,1], conviction du réseau
    """
    model, meta = _load_model()
    if model is None:
        return None
    try:
        import torch
        x = torch.tensor([assemble_live(symbol, votes)], dtype=torch.float32)
        with torch.no_grad():
            p = float(torch.sigmoid(model(x)).item())
        vote = max(-1.0, min(1.0, (p - 0.5) * 2.0))
        conf = abs(p - 0.5) * 2.0
        # edge hors-échantillon du DERNIER entraînement (val_acc - taux de base) :
        # exposé pour que la 16e voix puisse se taire tant qu'il n'est pas positif.
        try:
            val_edge = round(float(meta["val_acc"]) - float(meta["val_base_rate"]), 4)
        except (KeyError, TypeError, ValueError):
            val_edge = None
        return {"p_up": round(p, 4), "vote": round(vote, 4),
                "confidence": round(conf, 4), "val_edge": val_edge,
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
            samples.append((e.get("ts", 0), vector_from_votes(e.get("votes") or {}),
                            1 if ret > 0 else 0))
    samples.sort(key=lambda s: s[0])
    X = [s[1] for s in samples]
    y = [s[2] for s in samples]
    if with_ts:
        return X, y, [s[0] for s in samples]
    return X, y


def train(log_path=None, epochs=300, lr=1e-3, val_frac=0.2, batch_size=256,
          patience=60, verbose=True):
    """Entraîne le MLP de fusion et sérialise poids + méta. Retourne un dict de métriques.
    Déterministe (seed fixe, shuffle par Generator seedé). Nécessite torch (lève sinon —
    c'est une commande explicite). Split TEMPOREL PURGÉ : validation = les derniers
    val_frac dans le TEMPS (tous symboles confondus), et les échantillons de train dont
    la fenêtre d'étiquette mord sur la période de validation sont retirés (anti-fuite)."""
    import torch
    from torch import nn
    torch.manual_seed(SEED)

    X, y, ts = _dataset(log_path, with_ts=True)
    n = len(X)
    if n < 40:
        raise RuntimeError(f"trop peu d'exemples pour entraîner ({n}) — laisse tourner le cerveau")
    n_val = max(4, int(n * val_frac))
    val_start_ts = ts[n - n_val]
    cut = n - n_val
    while cut > 0 and ts[cut - 1] + HORIZON_S > val_start_ts:   # purge anti-fuite
        cut -= 1
    if cut < 20:
        raise RuntimeError(f"trop peu d'exemples de train après purge ({cut})")
    Xtr, ytr = X[:cut], y[:cut]
    Xva, yva = X[n - n_val:], y[n - n_val:]
    Xtr_t = torch.tensor(Xtr, dtype=torch.float32)
    ytr_t = torch.tensor(ytr, dtype=torch.float32).unsqueeze(1)
    Xva_t = torch.tensor(Xva, dtype=torch.float32)
    yva_t = torch.tensor(yva, dtype=torch.float32).unsqueeze(1)

    model = _build_net(torch, nn, len(FEATURES))
    # pos_weight : rééquilibre si les hausses/baisses sont déséquilibrées dans la fenêtre
    pos = sum(ytr) or 1
    neg = len(ytr) - sum(ytr) or 1
    loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor([neg / pos], dtype=torch.float32))
    opt = torch.optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    gen = torch.Generator().manual_seed(SEED)

    best_val, best_state, since_best = 1e9, None, 0
    for ep in range(epochs):
        model.train()
        perm = torch.randperm(len(Xtr_t), generator=gen)
        last_loss = 0.0
        for k in range(0, len(perm), batch_size):
            idx = perm[k:k + batch_size]
            opt.zero_grad()
            loss = loss_fn(model(Xtr_t[idx]), ytr_t[idx])
            loss.backward()
            opt.step()
            last_loss = float(loss.item())
        model.eval()
        with torch.no_grad():
            vloss = float(loss_fn(model(Xva_t), yva_t).item())
        if vloss < best_val - 1e-5:
            best_val, best_state, since_best = vloss, {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            since_best += 1
            if since_best >= patience:               # early-stopping : le val ne progresse plus
                if verbose:
                    print(f"arrêt anticipé à l'epoch {ep} (patience {patience})")
                break
        if verbose and ep % 20 == 0:
            print(f"epoch {ep:4d}  train {last_loss:.4f}  val {vloss:.4f}")

    model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        p_va = torch.sigmoid(model(Xva_t))
        va_pred = (p_va > 0.5).float()
        val_acc = float((va_pred == yva_t).float().mean().item())
        tr_pred = (torch.sigmoid(model(Xtr_t)) > 0.5).float()
        tr_acc = float((tr_pred == ytr_t).float().mean().item())
        brier = float(((p_va - yva_t) ** 2).mean().item())
        # précision quand le réseau a de la CONVICTION (|p-0.5| >= 0.10) : c'est la
        # zone où la 16e voix pèse ; c'est elle qu'il faut surveiller, pas l'accuracy brute
        hi_mask = (p_va - 0.5).abs() >= 0.10
        hi_n = int(hi_mask.sum().item())
        hi_acc = float((va_pred[hi_mask] == yva_t[hi_mask]).float().mean().item()) if hi_n else None
    up_rate = sum(yva) / len(yva)
    base_rate = round(max(up_rate, 1 - up_rate), 4)   # accuracy du prédicteur constant (repère)

    torch.save(model.state_dict(), WEIGHTS_PATH)
    try:
        version = int(json.loads(META_PATH.read_text(encoding="utf-8")).get("version", 0)) + 1
    except Exception:
        version = 1
    import datetime as _dt
    meta = {"version": version, "feature_hash": feature_hash(), "features": FEATURES,
            "arch": ARCH, "hidden": HIDDEN, "dropout": DROPOUT, "horizon_s": HORIZON_S,
            "deadband": DEADBAND, "source": str((Path(log_path) if log_path else
                                                 (HISTORY_PATH if HISTORY_PATH.exists() else REPO / "brain_log.json")).name),
            "n_samples": n, "n_train": cut, "n_val": n_val,
            "data_from": _dt.datetime.fromtimestamp(ts[0], _dt.timezone.utc).isoformat(timespec="seconds"),
            "data_to": _dt.datetime.fromtimestamp(ts[-1], _dt.timezone.utc).isoformat(timespec="seconds"),
            "train_acc": round(tr_acc, 4), "val_acc": round(val_acc, 4),
            "val_base_rate": base_rate, "val_brier": round(brier, 4),
            "val_hiconf_acc": round(hi_acc, 4) if hi_acc is not None else None,
            "val_hiconf_n": hi_n, "val_loss": round(best_val, 4), "seed": SEED,
            "trained_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")}
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _CACHE["loaded"] = False                          # force le rechargement au prochain predict
    if verbose:
        print(f"\nEntraîné sur {cut} exemples (val {n_val}, purge {n - n_val - cut}) — "
              f"{sum(y)} hausses / {n - sum(y)} baisses.")
        print(f"Accuracy — train {tr_acc:.3f} · val {val_acc:.3f} (base {base_rate:.3f}) · "
              f"Brier {brier:.4f} · haute-conf {hi_acc if hi_acc is None else round(hi_acc, 3)} sur {hi_n}")
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

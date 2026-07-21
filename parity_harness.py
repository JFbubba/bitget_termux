"""
parity_harness.py — HARNAIS DE PARITÉ live→recherche (SAVOIR §11.5, backlog PRIORITÉ 1).

Classement : SAFE. LECTURE SEULE du marché — aucun ordre, aucun secret. Ses seules
écritures : les sessions JSON dans un dossier dédié (injectable, ERR-019).

PRINCIPE (invariant SAVOIR §11.5) : la parité recherche→live est un HARNAIS, pas
un slogan. On CAPTURE une décision réelle du cerveau (`swarm_brain.peek`) en
enregistrant chaque donnée qui franchit les FRONTIÈRES de données, puis on REJOUE
le même chemin de décision en servant EXCLUSIVEMENT les données enregistrées (les
producteurs réseau ne sont JAMAIS rappelés). Même entrée → même décision,
exactement ; toute divergence = bug P0 (horloge cachée, état global mutable,
chemin de donnée non capturé), jamais un « détail d'arrondi ».

FRONTIÈRES interceptées (inventaire du 21/07 — couvrent le banc 14 + délégués) :
  - runtime_cache.get                   orderflow/macro/sentiment/derivs/liq + agents délégués
  - technicals.fetch_candles            technicals/divergent/structure/leadlag/esm/market_sources
  - bitget_market_data.market_snapshot  _price (invalidations §8) + repli orderflow
  - swarm_brain.load_weights            politique de poids du moment (fichier local)
Un chemin NON capturé se voit au rejeu : la frontière sert le repli et le compteur
« frontieres_manquantes » l'expose ; la divergence de vote le localise par agent.
Le REJEU DIFFÉRÉ peut aussi diverger par les POIDS si la politique locale (watch,
priors IC) a changé entre-temps — la comparaison sépare votes (chemin de donnée)
et weights (chemin de politique) pour distinguer les deux causes.

CLI :
  python parity_harness.py [SYMBOL]          # capture + rejeu immédiat → verdict
  python parity_harness.py --capture SYMBOL  # capture seule (session JSON)
  python parity_harness.py --rejeu FICHIER   # rejoue une session → verdict
  python parity_harness.py --status          # dernier verdict (lecture seule)
Code de sortie : 0 = PARITÉ, 1 = DIVERGENCE, 2 = erreur/session invalide.
"""

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SCHEMA = 1


def _dossier(dossier=None):
    d = Path(dossier or os.getenv("PARITY_DIR") or (ROOT / "parity_sessions"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def _cle(genre, args):
    """Clé canonique d'un enregistrement de frontière (JSON stable)."""
    try:
        return json.dumps([genre] + list(args), ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps([genre, repr(args)], ensure_ascii=False)


def _copie_json(v):
    """Copie profonde via JSON — garantit la rejouabilité (lève si non sérialisable)."""
    return json.loads(json.dumps(v))


class Frontieres:
    """Enveloppes de capture OU de rejeu sur les frontières de données.

    Context manager : les originaux sont TOUJOURS restaurés (fail-safe), même sur
    exception. Thread-safe (gather_votes vote en ThreadPool)."""

    def __init__(self, mode, magasin):
        assert mode in ("capture", "rejeu")
        self.mode = mode
        self.magasin = magasin          # clé -> valeur JSON
        self.verrou = threading.Lock()
        self.manquants = []             # frontières servies sans enregistrement (rejeu)
        self.non_rejouables = []        # valeurs non sérialisables (capture)
        self.collisions = []            # même clé, valeurs différentes dans UNE capture
        self._saves = []

    # -- installation / restauration -------------------------------------------
    def __enter__(self):
        import bitget_market_data
        import runtime_cache
        import swarm_brain
        import technicals
        self._patch(runtime_cache, "get", self._env_rc(runtime_cache.get))
        self._patch(technicals, "fetch_candles",
                    self._env_fn("candles", technicals.fetch_candles, defaut=[]))
        self._patch(bitget_market_data, "market_snapshot",
                    self._env_fn("snapshot", bitget_market_data.market_snapshot, defaut={}))
        if self.mode == "capture":
            orig_lw = swarm_brain.load_weights

            def lw():
                w = orig_lw()
                self._note("poids", (), w)
                return w
            self._patch(swarm_brain, "load_weights", lw)
        else:
            w = self.magasin.get(_cle("poids", ()))
            if w is not None:
                self._patch(swarm_brain, "load_weights", lambda: _copie_json(w))
        return self

    def __exit__(self, *exc):
        for mod, nom, orig in reversed(self._saves):
            setattr(mod, nom, orig)
        return False

    def _patch(self, mod, nom, nouveau):
        self._saves.append((mod, nom, getattr(mod, nom)))
        setattr(mod, nom, nouveau)

    # -- magasin ----------------------------------------------------------------
    def _note(self, genre, args, valeur):
        cle = _cle(genre, args)
        with self.verrou:
            try:
                v = _copie_json(valeur)
            except (TypeError, ValueError):
                self.non_rejouables.append(cle)
                return
            if cle in self.magasin and self.magasin[cle] != v:
                self.collisions.append(cle)   # 1re valeur conservée (déterminisme du rejeu)
                return
            self.magasin[cle] = v

    def _sers(self, genre, args, defaut):
        cle = _cle(genre, args)
        with self.verrou:
            if cle in self.magasin:
                return _copie_json(self.magasin[cle])
            self.manquants.append(cle)
        return defaut

    # -- enveloppes -------------------------------------------------------------
    def _env_rc(self, orig):
        harnais = self

        def get(key, ttl, producer, fallback=None, **kw):
            if harnais.mode == "capture":
                v = orig(key, ttl, producer, fallback=fallback, **kw)
                harnais._note("rc", (key,), v)
                return v
            return harnais._sers("rc", (key,), fallback)
        return get

    def _env_fn(self, genre, orig, defaut):
        harnais = self

        def fn(*args, **kw):
            args_cle = list(args) + sorted(kw.items())
            if harnais.mode == "capture":
                v = orig(*args, **kw)
                harnais._note(genre, args_cle, v)
                return v
            return harnais._sers(genre, args_cle, defaut)
        return fn


def _decision(symbol):
    """Exécute le chemin de décision RÉEL (swarm_brain.peek) et en extrait la
    partie comparable. L'observation de gather_votes est un passe-plat : le calcul
    n'est jamais remplacé (c'est la condition de la parité)."""
    import swarm_brain as sb
    votes_vus = {}
    orig_gv = sb.gather_votes

    def gv(sym):
        v = orig_gv(sym)
        votes_vus.update(v)
        return v

    sb.gather_votes = gv
    try:
        res = sb.peek(symbol)
    finally:
        sb.gather_votes = orig_gv
    extrait = {
        "votes": {n: {"vote": (d or {}).get("vote"), "confidence": (d or {}).get("confidence")}
                  for n, d in votes_vus.items()},
        "consensus": res.get("consensus"),
        "bias": res.get("bias"),
        "conviction": res.get("conviction"),
        "adjusted_conviction": res.get("adjusted_conviction"),
        "weights": res.get("weights"),
    }
    return extrait, res


def _comparer(avant, apres):
    """Divergences champ à champ (égalité EXACTE : mêmes entrées + même code =
    mêmes octets ; un « petit écart » est un bug, pas un arrondi)."""
    div = []

    def _diff(champ, a, b):
        if a != b:
            div.append({"champ": champ, "capture": a, "rejeu": b})

    agents = sorted(set(avant.get("votes") or {}) | set(apres.get("votes") or {}))
    for n in agents:
        va = (avant.get("votes") or {}).get(n) or {}
        vb = (apres.get("votes") or {}).get(n) or {}
        _diff(f"votes.{n}.vote", va.get("vote"), vb.get("vote"))
        _diff(f"votes.{n}.confidence", va.get("confidence"), vb.get("confidence"))
    for champ in ("consensus", "bias", "conviction", "adjusted_conviction"):
        _diff(champ, avant.get(champ), apres.get(champ))
    wa, wb = avant.get("weights") or {}, apres.get("weights") or {}
    for n in sorted(set(wa) | set(wb)):
        _diff(f"weights.{n}", wa.get(n), wb.get(n))
    return div


def capture(symbol="BTCUSDT", dossier=None):
    """Capture une décision réelle + toutes ses entrées. Rend le chemin de session."""
    symbol = symbol.upper()
    magasin = {}
    with Frontieres("capture", magasin) as f:
        t0 = time.time()
        extrait, _ = _decision(symbol)
        duree = round(time.time() - t0, 3)
    commit = ""
    try:
        import subprocess
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        pass
    session = {
        "schema": SCHEMA, "symbol": symbol, "ts": int(time.time()), "commit": commit,
        "duree_capture_s": duree, "decision": extrait, "magasin": magasin,
        "non_rejouables": f.non_rejouables, "collisions": f.collisions, "rejeux": [],
    }
    d = _dossier(dossier)
    chemin = d / f"parity_{symbol}_{session['ts']}.json"
    chemin.write_text(json.dumps(session, ensure_ascii=False))
    try:  # rotation : borne disque (sessions ~100 Ko), les plus récentes gagnent
        garder = int(os.getenv("PARITY_KEEP", "30"))
        fichiers = sorted(d.glob("parity_*.json"), key=lambda p: p.stat().st_mtime)
        for vieux in fichiers[:-garder]:
            vieux.unlink()
    except OSError:
        pass
    return chemin


def rejeu(chemin):
    """Rejoue une session enregistrée (AUCUN producteur réseau rappelé) et compare.
    Rend le verdict {parite, divergences, frontieres_manquantes, …}."""
    chemin = Path(chemin)
    session = json.loads(chemin.read_text())
    if session.get("schema") != SCHEMA:
        raise ValueError(f"schéma de session inconnu : {session.get('schema')!r}")
    with Frontieres("rejeu", session["magasin"]) as f:
        extrait, _ = _decision(session["symbol"])
    divergences = _comparer(session["decision"], extrait)
    verdict = {
        "ts": int(time.time()),
        "parite": not divergences,
        "divergences": divergences,
        "frontieres_manquantes": sorted(set(f.manquants)),
        "non_rejouables": session.get("non_rejouables", []),
    }
    try:  # trace du rejeu dans la session (best-effort : le verdict prime)
        session.setdefault("rejeux", []).append(verdict)
        chemin.write_text(json.dumps(session, ensure_ascii=False))
    except OSError:
        pass
    return verdict


def _imprimer_verdict(verdict, session_chemin=None):
    if verdict["parite"]:
        print("PARITÉ OK — même entrée → même décision (0 divergence)")
    else:
        print(f"DIVERGENCE — {len(verdict['divergences'])} champ(s) (bug P0 à expliquer) :")
        for d in verdict["divergences"][:20]:
            print(f"  · {d['champ']} : capture={d['capture']!r} → rejeu={d['rejeu']!r}")
        if len(verdict["divergences"]) > 20:
            print(f"  … +{len(verdict['divergences']) - 20} autres")
    if verdict["frontieres_manquantes"]:
        print(f"frontières non capturées servies en repli : {len(verdict['frontieres_manquantes'])}")
        for c in verdict["frontieres_manquantes"][:8]:
            print(f"  · {c}")
    if verdict.get("non_rejouables"):
        print(f"valeurs non sérialisables ignorées à la capture : {len(verdict['non_rejouables'])}")
    if session_chemin:
        print(f"session : {session_chemin}")


def _status(dossier=None):
    d = _dossier(dossier)
    fichiers = sorted(d.glob("parity_*.json"), key=lambda p: p.stat().st_mtime)
    if not fichiers:
        print("aucune session de parité enregistrée")
        return 2
    session = json.loads(fichiers[-1].read_text())
    rejeux = session.get("rejeux") or []
    print(f"dernière session : {fichiers[-1].name} (symbol {session.get('symbol')}, "
          f"commit {session.get('commit') or '?'}, {len(rejeux)} rejeu(x))")
    if not rejeux:
        print("jamais rejouée")
        return 2
    _imprimer_verdict(rejeux[-1])
    return 0 if rejeux[-1]["parite"] else 1


def main(argv):
    args = list(argv)
    try:
        if args and args[0] == "--status":
            return _status()
        if args and args[0] == "--rejeu":
            if len(args) < 2:
                print("usage : python parity_harness.py --rejeu FICHIER")
                return 2
            verdict = rejeu(args[1])
            _imprimer_verdict(verdict, args[1])
            return 0 if verdict["parite"] else 1
        if args and args[0] == "--capture":
            symbol = args[1] if len(args) > 1 else "BTCUSDT"
            chemin = capture(symbol)
            print(f"session capturée : {chemin}")
            return 0
        symbol = args[0] if args else "BTCUSDT"
        chemin = capture(symbol)
        verdict = rejeu(chemin)
        _imprimer_verdict(verdict, chemin)
        return 0 if verdict["parite"] else 1
    except Exception as exc:
        print(f"erreur harnais : {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

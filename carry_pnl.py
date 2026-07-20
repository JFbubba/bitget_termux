#!/usr/bin/env python3
"""carry_pnl.py — le carry RÉELLEMENT encaissé, net de frais. SAFE, LECTURE SEULE.

Pourquoi ce module existe (deep-research du 20/07/2026) : la campagne a établi que la capture
de funding est le SEUL edge non-directionnel avec un mécanisme structurel documenté, mais que
**100 % des magnitudes publiées sont BRUTES et in-sample** — recherche exhaustive des trois
papiers primaires : « out-of-sample » 0 occurrence, « deflated » 0, « net of » 0, « bps » 0.
Et la décroissance hors-échantillon est monotone (Sharpe 6,45 -> 4,06 en 2024 -> négatif 2025).

Donc : la seule mesure vraiment hors-échantillon dont nous disposons est NOTRE PROPRE registre.
Elle prime sur toute magnitude de littérature, et elle ne coûte rien — les lignes sont déjà là.

L'ARITHMÉTIQUE QUI COMMANDE TOUT : 21,84 %/an sur 1095 périodes de 8 h = ~1,99 bps BRUT par
règlement de funding, contre jusqu'à ~24 bps pour un aller-retour 2 jambes en taker. Churner la
couverture ne l'érode pas, elle l'ANNIHILE. D'où la métrique centrale de ce module —
**règlements de funding capturés PAR ALLER-RETOUR** : sous 1, on paie deux frais pour moins d'un
règlement, et le carry est structurellement perdant quel que soit le taux.

SOURCE : /api/v2/mix/account/bill (GET signé, lecture seule). Cet endpoint existe dans le client
mais n'est exposé par AUCUN outil CLI du hub — d'où le passage par real_positions._signed_get,
déjà utilisé par adl_rank/bitget_watch/futures_executor.
SCHÉMA RÉEL relevé le 2026-07-20 (mock des tests ancré dessus, ERR-007/009) :
  contract_settle_fee -> amount = funding (POSITIF = perçu, NÉGATIF = payé), fee = 0
  open_*              -> amount = 0,               fee NÉGATIF (coût)
  close_*             -> amount = PnL réalisé,     fee NÉGATIF (coût)
  trans_*             -> mouvements de trésorerie : IGNORÉS (ce n'est ni du funding ni un coût)

CE QUE CE MODULE NE MESURE PAS, et pourquoi c'est assumé : la jambe SPOT de la couverture. Le
carry est long spot / short perp ; le PnL directionnel des deux jambes se compense par
construction, et le funding moins les frais EST l'edge. Un net positif tiré du `realise_usdt`
(PnL de trading) n'est PAS du carry — le verdict le dit explicitement.

Aucun ordre, aucun mur touché. CLI : `python carry_pnl.py [--jours N]`.
"""
import sys
import time

# Classement par PRÉFIXE de businessType (jamais par mots-clés littéraux : ce module est SAFE et
# ne doit contenir aucun vocabulaire d'exécution — la porte security_agent le vérifie).
PREFIXE_ENTREE = "open_"
PREFIXE_SORTIE = "close_"
REGLEMENT = "contract_settle_fee"


def _est_trade(bt):
    """PURE. La ligne est-elle une entrée/sortie de position (les seules porteuses de frais) ?"""
    return bt.startswith(PREFIXE_ENTREE) or bt.startswith(PREFIXE_SORTIE)


def _f(v):
    """float tolérant : None/vide/illisible -> 0.0 (jamais d'exception)."""
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def agreger(rows, symboles=None):
    """PURE. Sépare funding / frais / réalisé par symbole, avec les signes RÉELS du registre.
    Les lignes illisibles ou sans symbole sont ignorées. Retourne {par_symbole, total}.

    `symboles` (itérable) restreint le PÉRIMÈTRE — indispensable pour l'attribution : le
    registre est celui du COMPTE, il mélange l'activité du bot et celle du propriétaire."""
    perim = {str(s).upper() for s in symboles} if symboles is not None else None
    par = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        bt = str(r.get("businessType") or "")
        sym = str(r.get("symbol") or "").upper()
        if not sym or (bt != REGLEMENT and not _est_trade(bt)):
            continue                       # virements et lignes hors périmètre : ni funding ni coût
        if perim is not None and sym not in perim:
            continue
        d = par.setdefault(sym, {"funding_usdt": 0.0, "frais_usdt": 0.0, "realise_usdt": 0.0,
                                 "n_reglements": 0, "n_ouvertures": 0, "n_fermetures": 0})
        d["frais_usdt"] += _f(r.get("fee"))            # DÉJÀ négatif dans le registre
        if bt == REGLEMENT:
            d["funding_usdt"] += _f(r.get("amount"))   # négatif = funding PAYÉ, il compte aussi
            d["n_reglements"] += 1
        elif bt.startswith(PREFIXE_ENTREE):
            d["n_ouvertures"] += 1
        else:
            d["realise_usdt"] += _f(r.get("amount"))
            d["n_fermetures"] += 1
    total = {"funding_usdt": 0.0, "frais_usdt": 0.0, "realise_usdt": 0.0,
             "n_reglements": 0, "n_ouvertures": 0, "n_fermetures": 0}
    for sym, d in par.items():
        d["net_usdt"] = round(d["funding_usdt"] + d["realise_usdt"] + d["frais_usdt"], 8)
        # Règlements par aller-retour BOUCLÉ : None si aucune fermeture (position encore
        # ouverte -> ratio indéfini, jamais une division par zéro ni un 0 trompeur).
        d["reglements_par_ar"] = (round(d["n_reglements"] / d["n_fermetures"], 6)
                                  if d["n_fermetures"] > 0 else None)
        for k in total:
            total[k] += d[k]
        for k in ("funding_usdt", "frais_usdt", "realise_usdt"):
            d[k] = round(d[k], 8)
    total["net_usdt"] = round(total["funding_usdt"] + total["realise_usdt"] + total["frais_usdt"], 8)
    total["reglements_par_ar"] = (round(total["n_reglements"] / total["n_fermetures"], 6)
                                  if total["n_fermetures"] > 0 else None)
    for k in ("funding_usdt", "frais_usdt", "realise_usdt"):
        total[k] = round(total[k], 8)
    return {"par_symbole": par, "total": total}


def verdict(agg):
    """PURE. Le carry paie-t-il ? La question est funding ENCAISSÉ vs FACTURE DE FRAIS —
    surtout pas le net global : un PnL directionnel gagnant masquerait un carry perdant.
    None si rien n'a encore été mesuré (aucun règlement) : absence de donnée ≠ verdict négatif."""
    f = _f(agg.get("funding_usdt"))
    frais = _f(agg.get("frais_usdt"))
    net = round(f + frais, 8)                      # frais déjà négatifs
    paie = None if int(agg.get("n_reglements") or 0) <= 0 else bool(net > 0)
    return {"carry_paie": paie, "funding_net_frais_usdt": net,
            "funding_usdt": round(f, 8), "frais_usdt": round(frais, 8)}


def charger_bills(jours=90, signed_get=None, pages_max=20, now=None):
    """Lit le registre de compte futures, paginé (idLessThan). Fail-safe -> [] si indisponible.
    Injectable pour les tests (signed_get)."""
    now = time.time() if now is None else now
    depuis_ms = (now - float(jours) * 86400) * 1000.0
    if signed_get is None:
        try:
            import real_positions as rp
            signed_get = rp._signed_get
        except Exception:
            return []
    rows, dernier = [], None
    for _ in range(int(pages_max)):
        params = {"productType": "USDT-FUTURES", "limit": "100"}
        if dernier:
            params["idLessThan"] = dernier
        try:
            d = signed_get("/api/v2/mix/account/bill", params)
        except Exception:
            break
        lot = (d.get("bills") if isinstance(d, dict) else d) or []
        if not isinstance(lot, list) or not lot:
            break
        rows.extend(lot)
        try:
            dernier = lot[-1].get("billId")
            if _f(lot[-1].get("cTime")) < depuis_ms:
                break
        except Exception:
            break
    return [r for r in rows if isinstance(r, dict) and _f(r.get("cTime")) >= depuis_ms]


def build_report(agg=None, jours=90):
    """Rapport texte, lecture seule."""
    agg = agreger(charger_bills(jours=jours)) if agg is None else agg
    t = agg["total"]
    v = verdict(t)
    lignes = [f"=== FUNDING RÉELLEMENT ENCAISSÉ ({jours} j, hors échantillon) ===",
              "  ⚠ PÉRIMÈTRE = LE COMPTE, PAS LE BOT. Le registre /mix/account/bill mélange",
              "    l'activité du bot et celle du propriétaire (trades manuels). Ne PAS lire ce",
              "    total comme « le carry du bot » : restreindre via --symboles pour attribuer."]
    if not t["n_reglements"] and not t["n_fermetures"]:
        lignes.append("  aucune ligne lisible sur la période (registre indisponible ?)")
        lignes.append("Lecture seule. VERDICT: SAFE")
        return "\n".join(lignes)
    etat = {True: "OUI", False: "NON", None: "pas encore mesurable"}[v["carry_paie"]]
    lignes += [
        f"  funding encaissé : {t['funding_usdt']:+.4f} $ sur {t['n_reglements']} règlements",
        f"  frais payés      : {t['frais_usdt']:+.4f} $ ({t['n_ouvertures']} ouvertures · "
        f"{t['n_fermetures']} fermetures)",
        f"  >> LE CARRY PAIE-T-IL ? {etat} — funding net de frais {v['funding_net_frais_usdt']:+.4f} $",
        f"  PnL de trading réalisé (PAS du carry, indicatif) : {t['realise_usdt']:+.4f} $",
        f"  règlements par aller-retour : "
        + (f"{t['reglements_par_ar']:.2f}" if t["reglements_par_ar"] is not None else "n/a")
        + "  (sous 1.00 = couverture CHURNÉE : deux frais pour moins d'un règlement)",
        "  --- par symbole (net = funding + réalisé + frais) ---",
    ]
    for sym, d in sorted(agg["par_symbole"].items(), key=lambda kv: kv[1]["net_usdt"], reverse=True):
        ratio = f"{d['reglements_par_ar']:.2f}" if d["reglements_par_ar"] is not None else "n/a"
        lignes.append(f"    {sym:12s} funding {d['funding_usdt']:+8.4f} · frais {d['frais_usdt']:+8.4f} "
                      f"· réalisé {d['realise_usdt']:+8.4f} · net {d['net_usdt']:+8.4f} "
                      f"· règl/AR {ratio}")
    lignes.append("Lecture seule — aucun ordre, aucun mur touché. VERDICT: SAFE")
    return "\n".join(lignes)


def main():
    jours, syms = 90, None
    if "--jours" in sys.argv:
        try:
            jours = float(sys.argv[sys.argv.index("--jours") + 1])
        except (IndexError, ValueError):
            pass
    if "--symboles" in sys.argv:                 # attribution : ex. --symboles BTCUSDT,LABUSDT
        try:
            syms = [s for s in sys.argv[sys.argv.index("--symboles") + 1].split(",") if s]
        except IndexError:
            pass
    print(build_report(agg=agreger(charger_bills(jours=jours), symboles=syms), jours=jours))


if __name__ == "__main__":
    main()

"""regime_gate.py — porte directionnelle régime-aware (LECTURE SEULE).

Classement : SAFE. Aucune écriture, aucun réseau opérationnel, aucun ordre,
aucun secret.

But : supprimer les signaux qui COMBATTENT la marée macro. Les résultats mesurés
montrent qu'en régime de peur (RISK_OFF), les LONG échouent massivement (win-rate
~18 %, même à forte conviction) alors que les SHORT tiennent. On demote donc les
décisions à contre-régime vers « NEUTRE » AVANT la construction du plan : plus de
plan, plus de side journalisé, aucune position suivie à contre-marée.

`gate_decision` et `effective_regime` sont PURES et testées (modèle
`confluence_score.confluence_score`). `fetch_regime_snapshot` ajoute le réseau
(macro FRED + Fear&Greed) et NE LÈVE JAMAIS : sur échec total, le régime effectif
est NEUTRE -> la porte est un no-op (comportement historique).
"""


LONG_DECISIONS = ("LONG POSSIBLE", "BIAIS LONG")
SHORT_DECISIONS = ("SHORT POSSIBLE", "BIAIS SHORT")


def gate_decision(decision, regime, neutral_label="NEUTRE"):
    """PURE. Demote une décision qui combat le régime macro.

    RISK_OFF -> les décisions LONG deviennent `neutral_label`.
    RISK_ON  -> les décisions SHORT deviennent `neutral_label`.
    NEUTRE / None / inconnu -> décision inchangée (porte transparente).
    """
    reg = str(regime or "").upper()
    if reg == "RISK_OFF" and decision in LONG_DECISIONS:
        return neutral_label
    if reg == "RISK_ON" and decision in SHORT_DECISIONS:
        return neutral_label
    return decision


def effective_regime(macro_regime, fng_value=None, fear_th=20, greed_th=80):
    """PURE. Régime effectif pour la porte.

    L'EXTRÊME du Fear&Greed PRIME sur le macro : <= fear_th -> RISK_OFF,
    >= greed_th -> RISK_ON, même à l'encontre du régime macro. Motif empirique :
    en peur extrême les LONG échouent massivement (win-rate ~18 %) alors même
    que le macro peut lire RISK_ON ; on veut alors couper les LONG, pas les
    SHORT. Hors extrême (F&G neutre, absent ou illisible), le régime macro
    (RISK_ON/RISK_OFF) fait foi ; sinon NEUTRE (porte transparente).
    """
    reg = str(macro_regime or "").upper()
    if fng_value is not None:
        try:
            v = float(fng_value)
        except (TypeError, ValueError):
            v = None
        if v is not None:
            if v <= fear_th:
                return "RISK_OFF"
            if v >= greed_th:
                return "RISK_ON"
    if reg in ("RISK_ON", "RISK_OFF"):
        return reg
    return "NEUTRE"


def fetch_regime_snapshot():
    """IMPUR mais FAIL-SAFE (ne lève jamais). Un seul appel par run de scan.

    Source primaire : macro_context.macro_snapshot() (FRED sans clé, toujours
    importable, se dégrade en NEUTRE). Fear&Greed via sentiment_index (best-effort).
    Sur échec total -> {"regime": "NEUTRE", "fng": None} -> porte no-op.
    """
    regime = "NEUTRE"
    try:
        import macro_context as mc
        regime = (mc.macro_snapshot() or {}).get("regime") or "NEUTRE"
    except Exception:
        regime = "NEUTRE"

    fng = None
    try:
        import sentiment_index as si
        snap = si.fetch_fear_greed()
        fng = snap.get("value") if snap else None
    except Exception:
        fng = None

    return {"regime": regime, "fng": fng}


def build_report():
    snap = fetch_regime_snapshot()
    eff = effective_regime(snap["regime"], snap["fng"])
    return ("=== PORTE DE RÉGIME (lecture seule) ===\n"
            f"Régime macro : {snap['regime']} | Fear&Greed : {snap['fng']}\n"
            f"Régime effectif (porte) : {eff}\n"
            "F&G extrême prime sur le macro (peur -> RISK_OFF, avidité -> RISK_ON)\n"
            "RISK_OFF coupe les LONG · RISK_ON coupe les SHORT · NEUTRE = transparent\n"
            "Aide à la décision uniquement. Aucun ordre. VERDICT: SAFE")


def main():
    print(build_report())


if __name__ == "__main__":
    main()

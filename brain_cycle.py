"""
brain_cycle.py — un cycle d'APPRENTISSAGE du cerveau par symbole (read + learn).

Classement : SAFE. Lit le marché (lecture seule) et écrit UNIQUEMENT brain_log.json
+ brain_weights.json. AUCUN ordre, ne touche jamais aux limites de risque.

Pourquoi (audit #9) : sans planification, swarm_brain.learn() n'était déclenché que
par une requête humaine -> EARCP de facto non entraîné, brain_weights incomplet
(6/11 agents). Ce script, lancé à chaque cycle par agent_control, journalise les votes
des 11 agents et fait apprendre les poids sur les décisions matures.
"""


def main():
    try:
        import universe
        symbols = list(universe.symbols())          # univers dynamique si activé, sinon SYMBOLS
    except Exception:
        try:
            import config
            symbols = list(config.SYMBOLS)
        except Exception:
            symbols = ["BTCUSDT"]
    import swarm_brain
    ok = 0
    for sym in symbols:
        try:
            swarm_brain.read(sym, do_learn=True)     # journalise + apprend (poids EARCP)
            ok += 1
        except Exception as exc:
            print(f"{sym}: {type(exc).__name__}")
    print(f"brain_cycle : {ok}/{len(symbols)} symboles appris. Aucun ordre. VERDICT: SAFE")


if __name__ == "__main__":
    main()

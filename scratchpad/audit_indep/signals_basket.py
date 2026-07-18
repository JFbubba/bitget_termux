"""
signals_basket.py — PANIER ÉLARGI, multi-secteurs, échelle COMPLÈTE (ERR-001).
Question : un signal qui « marche » sur crypto-majors tient-il HORS de ce bloc
(memes, métaux, actions, ETF) ? On réutilise la machinerie IC indépendante
(audit_core) et les 7 signaux causals (signals_indep). Lecture seule.

Pour chaque (TF, signal, horizon) on agrège l'IC de rang PAR SECTEUR :
  - IC moyen du secteur (moyenne des IC intra-symbole)
  - n = nb de symboles où la mesure est valide (assez de points/plis)
  - part de symboles de même signe que la moyenne du secteur
Puis un VERDICT de robustesse cross-secteur : combien de secteurs partagent le
signe de crypto-majors avec un |IC| matériel (>= 0.01).
"""
import numpy as np
import audit_core as ac
import signals_indep as si

# tf-ladder-ok : échelle COMPLÈTE explicite M1..W1 (ERR-001), comme ladder_check.
LADDER = [("1m", 8), ("5m", 4), ("15m", 4), ("30m", 2),
          ("1H", 2), ("4H", 1), ("1D", 1), ("1W", 1)]
HZ = (1, 4, 24, 96)
SIGNALS = ["momentum8", "rsi14", "dist_sma50", "donchian20", "supertrend", "vortex", "cmf"]

# panier par secteur (uniquement des symboles réellement présents dans data_history)
SECTORS = {
    "cryptoMaj":  ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
                   "ADAUSDT", "TRXUSDT", "LINKUSDT", "UNIUSDT"],
    "cryptoMeme": ["DOGEUSDT", "PEPEUSDT", "SHIBUSDT"],
    "metal":      ["XAUUSDT", "XAGUSDT"],
    "equity":     ["AAPLUSDT", "NVDAUSDT", "TSLAUSDT", "MSTRUSDT", "COINUSDT"],
    "etf":        ["SPYUSDT", "QQQUSDT"],
}
SEC_ORDER = ["cryptoMaj", "cryptoMeme", "metal", "equity", "etf"]
MATERIAL = 0.01   # seuil de matérialité d'un IC pour le verdict de concordance


def collect(gran, stride):
    """res_by_sym[(sec,sym)] = {(signal,h): (ic,t,nf)}  (ou absent si trop court)."""
    out = {}
    for sec in SEC_ORDER:
        for sym in SECTORS[sec]:
            try:
                m = si.measure(sym, gran, stride)
            except Exception:
                m = None
            if m:
                out[(sec, sym)] = m[0]
    return out


def sector_ic(res_by_sym, sec, signal, h):
    """(ic_moyen, n_sym, frac_meme_signe) pour un secteur, ou None si vide."""
    ics = []
    for (s, sym), res in res_by_sym.items():
        if s != sec:
            continue
        if (signal, h) in res:
            ics.append(res[(signal, h)][0])
    if not ics:
        return None
    ics = np.array(ics, float)
    mean = float(ics.mean())
    same = float(np.mean(np.sign(ics) == np.sign(mean))) if mean != 0 else 0.0
    return mean, len(ics), same


def verdict(row):
    """row : dict secteur -> (ic,n,frac). Combien de secteurs partagent le signe
    de cryptoMaj avec |IC|>=MATERIAL ? Renvoie une chaîne compacte."""
    if "cryptoMaj" not in row or row["cryptoMaj"] is None:
        return "pas de réf crypto-maj"
    ref = row["cryptoMaj"][0]
    if abs(ref) < MATERIAL:
        return "crypto-maj ~plat"
    others = [s for s in SEC_ORDER if s != "cryptoMaj" and row.get(s)]
    conc = [s for s in others if abs(row[s][0]) >= MATERIAL and np.sign(row[s][0]) == np.sign(ref)]
    return f"{len(conc)}/{len(others)} secteurs concordants (signe {'+' if ref>0 else '-'})"


def fmt_cell(v):
    if v is None:
        return f"{'--':>13}"
    ic, n, same = v
    return f"{ic:+.3f}/{n}/{same*100:3.0f}%"


def main():
    print("############################################################################")
    print("# PANIER ÉLARGI — IC de RANG (6 plis purgés) par SECTEUR, échelle complète  #")
    print("# cellule = IC_moyen / n_symboles / %même-signe.  IC<0 réversion, IC>0 mom. #")
    print("# secteurs : cryptoMaj(9) cryptoMeme(3) metal(2) equity(5) etf(2)           #")
    print("############################################################################")
    for gran, stride in LADDER:
        res_by_sym = collect(gran, stride)
        nsym = len(res_by_sym)
        if nsym == 0:
            print(f"\n===== TF {gran} : aucun symbole exploitable (échantillon/plis trop courts) =====")
            continue
        secs_present = [s for s in SEC_ORDER if any(k[0] == s for k in res_by_sym)]
        print(f"\n===== TF {gran} — {nsym} symboles valides, secteurs présents : "
              f"{', '.join(secs_present)} =====")
        for h in HZ:
            print(f"\n  --- horizon h={h} barres ---")
            header = f"  {'signal':<11}" + "".join(f"{s:>14}" for s in SEC_ORDER) + "   | verdict"
            print(header)
            for sig in SIGNALS:
                row = {s: sector_ic(res_by_sym, s, sig, h) for s in SEC_ORDER}
                cells = "".join(f"{fmt_cell(row[s]):>14}" for s in SEC_ORDER)
                print(f"  {sig:<11}{cells}   | {verdict(row)}")
    print("\n\nLecture : un signal 'robuste cross-secteur' = même signe sur crypto-maj ET")
    print("les secteurs non-crypto (metal/equity/etf) avec |IC|>=0.01. Cases '--' =")
    print("échantillon trop court pour 6 plis purgés (honnête : profondeur haut-TF fine).")


if __name__ == "__main__":
    main()

"""
git_version.py — rapport Git LECTURE SEULE (version + santé du dépôt).

Classement : SAFE.
  - n'exécute que des commandes git en lecture (rev-parse, describe, log, status)
  - n'envoie aucun ordre, ne touche jamais au trading
  - n'affiche AUCUN secret : pas d'URL distante, pas de token, pas de .env

Commande Telegram associée : /git_version
Usage CLI :
    python git_version.py

Si le dossier courant n'est pas un dépôt git, le rapport reste lisible
(champs à "?") sans planter.
"""

import subprocess


def _run_git(args):
    """Exécute une commande git en lecture seule. Retourne (ok, sortie)."""
    try:
        result = subprocess.run(
            ["git"] + args,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return False, "git introuvable"
    except subprocess.TimeoutExpired:
        return False, "git timeout"

    if result.returncode != 0:
        return False, (result.stderr or result.stdout).strip()

    return True, result.stdout.strip()


def collect_git_info():
    """Retourne un dict de champs Git en lecture seule (aucun secret)."""
    info = {}

    ok, out = _run_git(["rev-parse", "--short", "HEAD"])
    info["commit_short"] = out if ok else "?"

    ok, out = _run_git(["log", "-1", "--pretty=%s"])
    info["subject"] = out if ok else "?"

    ok, out = _run_git(
        ["log", "-1", "--pretty=%cd", "--date=format:%Y-%m-%d %H:%M:%S"]
    )
    info["commit_date"] = out if ok else "?"

    ok, out = _run_git(["rev-parse", "--abbrev-ref", "HEAD"])
    info["branch"] = out if ok else "?"

    # Dernier tag accessible depuis HEAD (tag stable de préférence).
    ok, out = _run_git(["describe", "--tags", "--abbrev=0"])
    info["last_tag"] = out if ok else "(aucun tag)"

    # Tag(s) pointant exactement sur HEAD, le cas échéant.
    ok, out = _run_git(["tag", "--points-at", "HEAD"])
    info["tag_at_head"] = out if (ok and out) else ""

    # État de l'arbre de travail (propre / modifié).
    ok, out = _run_git(["status", "--porcelain"])
    if ok:
        changed = [line for line in out.splitlines() if line.strip()]
        info["dirty"] = bool(changed)
        info["changed_count"] = len(changed)
    else:
        info["dirty"] = None
        info["changed_count"] = 0

    # Avance / retard vs branche amont (si configurée). Jamais d'URL distante.
    ok, out = _run_git(["rev-list", "--left-right", "--count", "@{upstream}...HEAD"])
    if ok and out:
        parts = out.split()
        if len(parts) == 2:
            info["behind"] = parts[0]
            info["ahead"] = parts[1]

    return info


def build_report(info):
    """Formate le dict en texte lisible (Telegram / CLI). Aucun secret."""
    lines = ["=== GIT VERSION ==="]
    lines.append(f"Branche      : {info.get('branch', '?')}")
    lines.append(f"Commit       : {info.get('commit_short', '?')}")
    lines.append(f"Sujet        : {info.get('subject', '?')}")
    lines.append(f"Date commit  : {info.get('commit_date', '?')}")

    tag_at_head = info.get("tag_at_head") or ""
    if tag_at_head:
        lines.append(f"Tag (HEAD)   : {tag_at_head}")
    else:
        lines.append(f"Dernier tag  : {info.get('last_tag', '(aucun tag)')}")

    dirty = info.get("dirty")
    if dirty is None:
        etat = "inconnu (hors dépôt git ?)"
    elif dirty:
        etat = f"MODIFIÉ ({info.get('changed_count', 0)} fichier(s) non commit)"
    else:
        etat = "propre"
    lines.append(f"Arbre travail: {etat}")

    if "ahead" in info and "behind" in info:
        ahead = info["ahead"]
        behind = info["behind"]
        if ahead == "0" and behind == "0":
            lines.append("Vs amont     : à jour")
        else:
            lines.append(f"Vs amont     : {ahead} en avance / {behind} en retard")

    lines.append("")
    lines.append("Mode: lecture seule. Aucun ordre réel. VERDICT: SAFE")
    return "\n".join(lines)


def main():
    print(build_report(collect_git_info()))


if __name__ == "__main__":
    main()

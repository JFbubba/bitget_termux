"""Tests du garde-fou PreToolUse `.claude/hooks/guard.py` (v2 segments).

Contexte (audit frictions 22/07/2026) : la v1 faisait de la correspondance de
SOUS-CHAINE sur toute la commande, ce qui a produit 7+ faux positifs en 4 jours :
  - `git commit -m "... .env ..."` bloque a cause du MESSAGE de commit ;
  - `echo "(sans --confirm)"; python spot_executor.py --usdt 5` bloque a cause
    du texte d'affichage ;
  - `grep -nE "place.*order|bgc |withdraw"` bloque a cause du motif de grep.
Chaque faux positif entrainait un cycle gates.sh rejoue (~2 min) et, pire, le
reflexe appris de REFORMULER pour cacher le mot — un garde qu'on apprend a
contourner ne protege plus. La v2 analyse PAR SEGMENT D'EXECUTION et bloque
l'indirection non verifiable ($VAR, $(...), backticks) dans un segment sensible.

Ces tests verrouillent les deux faces : les faux positifs restent morts, les
murs restent debout. Le hook n'est pas suivi par git (outillage local de la
machine aux vraies cles) : skip propre si absent, la 4e porte reste verte sur
un clone.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / ".claude" / "hooks" / "guard.py"

pytestmark = pytest.mark.skipif(
    not GUARD.exists(), reason="hook local absent (clone sans .claude/hooks)"
)


def _run(payload):
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=payload if isinstance(payload, str) else json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=10,
    )
    return proc.returncode, proc.stderr


def _bash(cmd):
    return {"tool_name": "Bash", "tool_input": {"command": cmd}}


# ---------------------------------------------------------------- fail-open

def test_stdin_invalide_fail_open():
    code, _ = _run("pas du json {")
    assert code == 0


def test_outil_non_bash_passe():
    code, _ = _run({"tool_name": "Read", "tool_input": {"file_path": ".env"}})
    assert code == 0


def test_commande_vide_passe():
    code, _ = _run(_bash("   "))
    assert code == 0


# ------------------------------------------------- regle 1 : spot_executor

def test_spot_executor_confirm_bloque():
    code, err = _run(_bash("python spot_executor.py --usdt 5 --confirm"))
    assert code == 2 and "REEL" in err


def test_spot_executor_dry_passe():
    # Etape D du skill run-bitget : la preuve DRY doit etre executable.
    code, _ = _run(_bash("python spot_executor.py --usdt 5 2>&1 | tail -n 12"))
    assert code == 0


def test_spot_executor_confirm_dans_echo_ne_bloque_plus():
    # Faux positif historique (session bf02ea34, 20/07) : le texte d'affichage
    # contenait "--confirm", la commande reelle etait DRY.
    code, _ = _run(_bash(
        'echo "--- spot_executor DRY (sans --confirm) ---" && '
        "python spot_executor.py --usdt 5 2>&1 | tail -n 12"
    ))
    assert code == 0


def test_spot_executor_indirection_bloquee():
    # Fail-safe : des arguments non verifiables ne passent pas.
    code, err = _run(_bash("python spot_executor.py $FLAGS"))
    assert code == 2 and "indirection" in err


# --------------------------------------- regle 2 : accumulation_engine

def test_accumulation_engine_script_bloque():
    code, err = _run(_bash("python accumulation_engine.py"))
    assert code == 2 and "accumulation_engine" in err


def test_accumulation_engine_import_c_passe():
    code, _ = _run(_bash(
        "python -c \"import accumulation_engine; print(accumulation_engine.analyze())\""
    ))
    assert code == 0


# ------------------------------------------------------- regle 3 : bgc

def test_bgc_verbe_ordre_bloque():
    code, err = _run(_bash("bgc spot_place_order BTCUSDT buy 10"))
    assert code == 2 and "bgc" in err


def test_bgc_verbe_ordre_apres_wrapper_bloque():
    code, _ = _run(_bash("timeout 30 bgc close_position BTCUSDT"))
    assert code == 2


def test_bgc_lecture_seule_passe():
    code, _ = _run(_bash("bgc account_balance"))
    assert code == 0


def test_bgc_indirection_bloquee():
    code, _ = _run(_bash("bgc $VERB BTCUSDT"))
    assert code == 2


def test_grep_motif_bgc_ne_bloque_plus():
    # Faux positif historique (session 2cb3de85, 18/07) : un grep d'AUDIT
    # prouvant l'ABSENCE de ces motifs etait lui-meme bloque.
    code, _ = _run(_bash(
        'git status && grep -nE "place.*order|bgc |withdraw|transfer" lab_*.py'
    ))
    assert code == 0


# --------------------------------------------------- regle 4 : git add

def test_git_add_env_bloque():
    code, err = _run(_bash("git add .env"))
    assert code == 2 and ".env" in err


def test_git_add_env_force_bloque():
    code, _ = _run(_bash("git add -f .env"))
    assert code == 2


def test_git_add_env_example_passe():
    code, _ = _run(_bash("git add .env.example"))
    assert code == 0


def test_env_dans_message_de_commit_ne_bloque_plus():
    # LE faux positif principal (4 sessions en 4 jours : 1563edad, 8431e002,
    # eaa8ce87, 3c1c09d3) : `.env` mentionne dans le -m d'un commit chaine
    # apres un git add legitime.
    code, _ = _run(_bash(
        "bash gates.sh && git add accumulation_engine.py && "
        "git commit -m \"fix : l'armement passe par .env, charge a l'import\""
    ))
    assert code == 0


def test_git_add_global_A_bloque():
    code, err = _run(_bash("git add -A"))
    assert code == 2 and "NOMINATIVEMENT" in err


def test_git_add_global_all_bloque():
    code, _ = _run(_bash("git add --all"))
    assert code == 2


def test_git_add_point_bloque():
    code, _ = _run(_bash("git add ."))
    assert code == 2


def test_git_add_point_en_second_argument_bloque():
    code, _ = _run(_bash("git add fichier.py ."))
    assert code == 2


def test_git_add_flags_combines_avec_A_bloques():
    code, _ = _run(_bash("git add -Av"))
    assert code == 2


def test_git_add_chemin_relatif_passe():
    # `git add ./fichier.py` et les chemins .claude/... ne sont PAS le staging
    # global `git add .`.
    code, _ = _run(_bash("git add ./dashboard/server.py .claude/settings.json"))
    assert code == 0


def test_git_add_nominatif_passe():
    code, _ = _run(_bash(
        "git add swarm_brain.py tests/test_guard.py && git commit -m \"tests\""
    ))
    assert code == 0


def test_git_add_indirection_bloquee():
    code, _ = _run(_bash("git add $(git diff --name-only)"))
    assert code == 2


def test_git_add_A_cite_dans_message_de_commit_ne_bloque_pas():
    # Attrape en conditions reelles le 22/07 : le commit DOCUMENTANT la regle
    # contenait litteralement "git add -A / git add ." dans son message — la
    # regle ne s'applique qu'au git add en POSITION DE COMMANDE d'un segment.
    code, _ = _run(_bash(
        "git add guard_doc.md && "
        "git commit -m \"regle : git add -A / git add . interdit, liste nominative\""
    ))
    assert code == 0


def test_git_add_backtick_bloque():
    code, _ = _run(_bash("git add `git diff --name-only`"))
    assert code == 2

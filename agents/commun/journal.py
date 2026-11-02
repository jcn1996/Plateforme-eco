"""Journal (logs) lisible dans l'onglet Actions de GitHub."""
import logging
import sys


def journal(nom: str) -> logging.Logger:
    """Renvoie un journal qui écrit sur la sortie standard avec l'heure et le niveau."""
    j = logging.getLogger(nom)
    if not j.handlers:
        sortie = logging.StreamHandler(sys.stdout)
        sortie.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s — %(message)s", "%H:%M:%S"))
        j.addHandler(sortie)
        j.setLevel(logging.INFO)
        j.propagate = False
    return j

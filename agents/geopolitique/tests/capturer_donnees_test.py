"""Enregistre des réponses réelles comme données de test (python -m agents.geopolitique.tests.capturer_donnees_test).
L'API DOC de GDELT n'est pas capturée ici (elle limite les adresses partagées) : ses fichiers
gdelt_doc_*.json sont rédigés au format ArtList, à partir d'articles réels."""
import io
import json
import zipfile
from datetime import date, timedelta
from pathlib import Path

from agents.geopolitique.sources import GDELT_EXPORT, OFAC_ACTIONS, FournisseurReel
from agents.geopolitique.agent import charger_config

DOSSIER = Path(__file__).resolve().parent / "donnees"


def main():
    config = charger_config()
    f = FournisseurReel(Path(__file__).resolve().parents[2] / ".cache", config)
    for s in config["sources_rss"]:
        if s["url"]:
            try:
                (DOSSIER / f"rss_{s['cle']}.xml").write_text(f.t.texte(s["url"]), encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                print(s["cle"], e)
    (DOSSIER / "ofac.html").write_text(f.t.texte(OFAC_ACTIONS), encoding="utf-8")
    depuis = (date.today() - timedelta(days=3)).isoformat()
    fr = f.federal_register(config["federal_register"]["agences"], depuis)
    (DOSSIER / "federal_register.json").write_text(json.dumps({"results": [
        {"title": d["titre"], "html_url": d["url"], "publication_date": d["date"][:10], "type": d["type"],
         "abstract": d["description"] or None, "agencies": [{"name": a} for a in d["agences"]]} for d in fr]}, ensure_ascii=False, indent=1), encoding="utf-8")
    import re
    h = re.search(r"/(\d{14})\.export", f.t.texte("https://data.gdeltproject.org/gdeltv2/lastupdate.txt")).group(1)
    with zipfile.ZipFile(io.BytesIO(f.t.octets(GDELT_EXPORT.format(horodatage=h)))) as z:
        (DOSSIER / "gdelt_export.csv").write_text(z.read(z.namelist()[0]).decode("utf-8", errors="replace"), encoding="utf-8")
    (DOSSIER / "gpr.json").write_text(json.dumps(f.gpr()[-400:]), encoding="utf-8")
    (DOSSIER / "epu.json").write_text(json.dumps(f.epu((date.today() - timedelta(days=60)).isoformat())[0]), encoding="utf-8")


if __name__ == "__main__":
    main()

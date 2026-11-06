"""Met à jour les données de test de l'agent flux à partir des vraies sources (réseau requis) :

    python -m agents.flux.tests.capturer_donnees_test

- fmi_imts.csv : réponse réelle du FMI (IMTS), réduite aux colonnes utiles et à 4 mois
  (les deux derniers et les mêmes mois un an plus tôt) pour rester légère ;
- comtrade_AAAAMM.json : réponses réelles de UN Comtrade (aperçu public) pour un mois et le même mois
  un an plus tôt, regroupées en un fichier par mois.
Les tests utilisent la date simulée DATE_TEST : Comtrade y essaie d'abord le mois M-2.
"""
import csv
import io
import json
from datetime import datetime, timezone

from agents.flux import agent

DATE_TEST = "2026-08-20"
MOIS_FMI = ["2025-06", "2025-07", "2026-06", "2026-07"]


def main() -> None:
    t = agent.Telechargeur(agent.RACINE / "agents" / ".cache" / "flux", delai_politesse=3.0)
    codes = list(agent.CONFIG["pays"])
    iso3 = "+".join(agent.CONFIG["pays"][c]["iso3"] for c in codes)
    texte = t.texte(agent.FMI_URL.format(decl=iso3, part=iso3), params={"startPeriod": MOIS_FMI[0], "detail": "dataonly"},
                    entetes=agent.FMI_CSV)
    colonnes = ["COUNTRY", "INDICATOR", "COUNTERPART_COUNTRY", "TIME_PERIOD", "OBS_VALUE"]
    sortie = io.StringIO()
    w = csv.writer(sortie, lineterminator="\n")
    w.writerow(colonnes)
    for r in csv.DictReader(io.StringIO(texte)):
        if r["TIME_PERIOD"].replace("-M", "-") in MOIS_FMI:
            w.writerow([r[c] for c in colonnes])
    (agent.DONNEES_TEST / "fmi_imts.csv").write_text(sortie.getvalue(), encoding="utf-8")

    m49 = sorted(agent.CONFIG["pays"][c]["m49"] for c in codes)
    p = agent.decaler(agent.mois_de(datetime.fromisoformat(DATE_TEST).replace(tzinfo=timezone.utc)), -2)
    for mois in (p, agent.decaler(p, -12)):
        lignes = []
        for i in range(0, len(m49), 4):
            r = t.json(agent.COMTRADE_URL, params={"reporterCode": ",".join(map(str, m49[i:i + 4])), "period": mois.replace("-", ""),
                                                   "partnerCode": ",".join(map(str, m49)), "flowCode": "X,M", "cmdCode": "TOTAL"})
            garder = ("reporterCode", "partnerCode", "partner2Code", "flowCode", "customsCode", "motCode", "period", "primaryValue")
            lignes += [{k: x.get(k) for k in garder} for x in r.get("data") or []]
        (agent.DONNEES_TEST / f"comtrade_{mois.replace('-', '')}.json").write_text(
            json.dumps({"data": lignes}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
        print(mois, len(lignes), "lignes Comtrade")


if __name__ == "__main__":
    main()

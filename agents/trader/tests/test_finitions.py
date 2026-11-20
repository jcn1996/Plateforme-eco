"""Finitions avant la période de test (sans changer aucune règle de sélection) : achat réduit faute de liquidités puis
complété, étiquettes de poche des lignes héritées, portefeuille « momentum seul » et bilan du mois.
Données construites de toutes pièces (ni config/ ni data/ réels)."""
from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agents.trader import bilan as BI
from agents.trader import portefeuille as P
from agents.trader import strategie as S
from agents.trader.agent import charger_config

T = datetime(2026, 11, 20, 15, 5, tzinfo=timezone.utc)


def position(sym, poche, valeur, ligne_id, nom=None):
    return {"symbole": sym, "nom": nom or sym, "poche": poche, "ligne_id": ligne_id, "classe": "actions", "devise": "USD", "quantite": 100,
            "valeur_eur": valeur, "dernier_cours_eur": valeur / 100, "prix_revient_eur": valeur / 100, "prix_revient_local": valeur / 110,
            "cout_total_eur": valeur, "frais_eur": 0.0, "type": "entreprises"}


class TestComplementEtEtiquettes(unittest.TestCase):
    def setUp(self):
        self.config = charger_config()
        self.etat = {
            "liquidites": 5149.0, "dernier_reequilibrage": "2026-11", "ordres": [],
            "positions": {"UNG": position("UNG", "matieres", 3924.0, "matiere-gaz_us", "United States Natural Gas Fund"),
                          "CNX": position("CNX", "satellite", 6900.0, "entreprise-CNX"), "EWW": position("EWW", "coeur", 4170.0, "pays-MX"),
                          "PTON": position("PTON", "entreprises", 6460.0, "selection-PTON")},
            "historique": {"2026-11-16": {"portefeuille": 99000.0}},
            "derniere_decision": {"cibles": {"lignes": [
                {"symbole": "UNG", "poche": "matieres", "cible": 8, "ligne_id": "matiere-gaz_us", "nom": "UNG"},
                {"symbole": "CNX", "poche": "entreprises", "cible": 7.0, "ligne_id": "selection-CNX", "nom": "CNX"},
                {"symbole": "EWW", "poche": "pays", "cible": 4.33, "ligne_id": "pays-MX", "nom": "EWW"},
                {"symbole": "PTON", "poche": "entreprises", "cible": 7.0, "ligne_id": "selection-PTON", "nom": "PTON"}]}}}
        self.valo = {"valeur": 93658.0, "liquidites": 5149.0}
        # achat d'entrée du 16/11 exécuté pour 3 767,53 € seulement (ventes asiatiques pas encore exécutées)
        self.ops = [{"id": "o00105", "date": "2026-11-16T14:30:00Z", "sens": "achat", "symbole": "UNG", "montant_eur": 3767.53,
                     "motif": "entrée matieres", "raison": {"cible_pct": 8, "poids_actuel_pct": 0.0}},
                    {"id": "o00106", "date": "2026-11-16T14:30:00Z", "sens": "achat", "symbole": "PTON", "montant_eur": 7100.76,
                     "motif": "entrée entreprises", "raison": {"cible_pct": 7.0, "poids_actuel_pct": 0.0}}]

    def test_reetiquetage_des_lignes_heritees(self):
        faits = S.reetiqueter(self.etat, T)
        self.assertEqual({(r["symbole"], r["de"], r["vers"]) for r in faits}, {("CNX", "satellite", "entreprises"), ("EWW", "coeur", "pays")})
        self.assertEqual(self.etat["positions"]["CNX"]["ligne_id"], "selection-CNX")
        # la valeur change de poche comme un flux : le suivi par poche reste juste, l'historique n'est pas réécrit
        self.assertEqual(self.etat["flux_poches"]["2026-11-20"], {"satellite": -6900.0, "entreprises": 6900.0, "coeur": -4170.0, "pays": 4170.0})
        self.assertEqual(self.etat["historique"], {"2026-11-16": {"portefeuille": 99000.0}})
        self.assertEqual(S.reetiqueter(self.etat, T), [], "idempotent")

    def test_complement_de_l_achat_reduit(self):
        ordres = S.completer_entrees(self.etat, self.valo, self.ops, self.config, T)
        self.assertEqual([o["symbole"] for o in ordres], ["UNG"], "PTON a été exécuté à sa cible : rien à compléter")
        o = ordres[0]
        self.assertEqual(o["motif"], "complément d'exécution")
        self.assertAlmostEqual(o["montant_eur"], 8 / 100 * 93658 - 3924, delta=1)
        self.assertIn("faute de liquidités", o["raison"]["texte"])
        self.assertEqual(self.etat["complements_verifies"], "2026-11")
        # après exécution du complément, chaque ligne est à sa cible à 1 point près
        self.etat["positions"]["UNG"]["valeur_eur"] += o["montant_eur"]
        S.reetiqueter(self.etat, T)
        self.assertEqual(S.ecarts_aux_cibles(self.etat, self.valo, 1), [])
        self.assertEqual(S.completer_entrees(self.etat, self.valo, self.ops, self.config, T), [], "une seule fois")

    def test_pas_de_complement_tant_que_des_ventes_attendent(self):
        self.etat["ordres"] = [{"symbole": "5108.T", "sens": "vente", "statut": "en attente", "montant_eur": 3477.0}]
        self.assertEqual(S.completer_entrees(self.etat, self.valo, self.ops, self.config, T), [])
        self.assertIn("UNG", self.etat["complements"])

    def test_execution_reduite_notee(self):
        etat = {"liquidites": 3800.0, "positions": {}, "ordres": []}
        o = {"id": "o1", "cree_le": "2026-11-16T07:46:00Z", "sens": "achat", "symbole": "UNG", "nom": "UNG", "devise": "USD", "montant_eur": 8000.0, "poche": "matieres", "type": "matieres",
             "ligne_id": "matiere-gaz_us", "raison": {"cible_pct": 8}}
        op = P._acheter(etat, o, {"prix": 10.0, "le": "2026-11-16T14:30:00Z"}, {"USD": 1.1, "EUR": 1.0}, self.config)
        self.assertIsNotNone(op)
        self.assertLess(op["montant_eur"], 3800)
        self.assertIn("UNG", etat["complements"])
        self.assertGreater(etat["complements"]["UNG"]["manque_eur"], 4000)

    def test_achat_dans_une_position_heritee_la_reetiquette(self):
        etat = {"liquidites": 10000.0, "positions": {"CNX": position("CNX", "satellite", 3500.0, "entreprise-CNX")}, "ordres": []}
        o = {"id": "o2", "cree_le": "2026-11-16T07:46:00Z", "sens": "achat", "symbole": "CNX", "nom": "CNX", "devise": "USD", "montant_eur": 3480.0, "poche": "entreprises", "type": "entreprises",
             "ligne_id": "selection-CNX", "raison": {"cible_pct": 7.0}}
        P._acheter(etat, o, {"prix": 35.0, "le": "2026-11-16T14:30:00Z"}, {"USD": 1.1, "EUR": 1.0}, self.config)
        self.assertEqual((etat["positions"]["CNX"]["poche"], etat["positions"]["CNX"]["ligne_id"]), ("entreprises", "selection-CNX"))


def hebdo(depart: float, fin: float, debut="2025-10-31", semaines=56):
    from datetime import date, timedelta
    d0 = date.fromisoformat(debut)
    return [[(d0 + timedelta(weeks=i)).isoformat(), round(depart + (fin - depart) * i / (semaines - 1), 4)] for i in range(semaines)]


class TestBilan(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        (self.data / "entreprises" / "fiches").mkdir(parents=True)
        societes = []
        for i in range(10):
            t = f"S{i}"
            societes.append({"ticker": t, "pays": "US", "secteur_gics": "Industrials", "capitalisation_md": 10, "financier": None, "holding": False,
                             "fiche": f"data/entreprises/fiches/{t}.json"})
            (self.data / "entreprises" / "fiches" / f"{t}.json").write_text(json.dumps({"donnees": {"cours_hebdo": hebdo(100, 100 + 10 * i)}}), encoding="utf-8")
        societes.append({"ticker": "BANQ", "pays": "US", "secteur_gics": "Financials", "capitalisation_md": 50, "fiche": "x"})
        (self.data / "entreprises.json").write_text(json.dumps({"donnees": societes}), encoding="utf-8")
        self.cfg = {"entreprises": {"pays": ["US"], "secteurs_exclus": ["Financials", "Real Estate"], "capitalisation_min_md": 2}}

    def tearDown(self):
        self.tmp.cleanup()

    def test_momentum_seul_et_bilan(self):
        etat = {"historique": {"2026-11-16": {"portefeuille": 99000.0, "msci_world": 100000.0},
                               "2026-11-30": {"portefeuille": 93500.0, "msci_world": 96000.0}}}
        m = BI.suivre_momentum(etat, self.data, self.cfg, "2026-11-20")
        mois = m["mois"]["2026-11"]
        self.assertEqual(mois["date"], "2026-11-16")
        self.assertEqual(mois["univers"], 10, "société financière exclue")
        self.assertEqual(sorted(mois["composition"]), ["S8", "S9"], "les 20 % les plus forts sur 12 mois hors dernier mois")
        self.assertIn("2026-11-20", m["historique"])
        BI.suivre_momentum(etat, self.data, self.cfg, "2026-11-30")
        chef = {"liste": {"mois": "2026-12", "mouvements": [], "mois_precedent": {"mois": "2026-11", "mouvements": [
            {"date": "2026-11-16", "sens": "entrée", "id": "pays-MX", "nom": "Mexique", "texte": "Entrée · Mexique"},
            {"date": "2026-11-24", "sens": "sortie", "id": "selection-PTON", "nom": "Peloton", "texte": "Sortie · Peloton"}]}}}
        obs = {"resume": {"achat_dirigeant": {"libelle": "Achats de dirigeants", "enregistres": 590,
                                              "horizons": {"1": {"n": 40, "battent_indice_pct": 55.0, "ecart_moyen_points": 0.8}}}}}
        self.assertIsNone(BI.ecrire_bilan_si_du(etat, self.data, chef, obs, datetime(2026, 11, 30, 8, tzinfo=timezone.utc)), "pas avant le 1er")
        chemin = BI.ecrire_bilan_si_du(etat, self.data, chef, obs, datetime(2026, 12, 1, 7, 40, tzinfo=timezone.utc))
        b = json.loads(chemin.read_text(encoding="utf-8"))["donnees"]
        perf = {p["nom"]: p for p in b["performances"]}
        self.assertAlmostEqual(perf["Portefeuille démo (trader)"]["mois_pct"], -5.56, places=2)
        self.assertAlmostEqual(perf["MSCI World (en euros)"]["depuis_debut_pct"], -4.0, places=2)
        self.assertIsNotNone(perf["Portefeuille « momentum seul »"]["depuis_debut_pct"])
        self.assertEqual([m["nom"] for m in b["liste"]["entrees"]], ["Mexique"])
        self.assertEqual([m["nom"] for m in b["liste"]["sorties"]], ["Peloton"])
        self.assertEqual(b["observation"]["achat_dirigeant"]["battent_indice_pct"], 55.0)
        self.assertEqual(json.loads((self.data / "bilan" / "index.json").read_text(encoding="utf-8"))["donnees"], ["2026-11"])
        self.assertIsNone(BI.ecrire_bilan_si_du(etat, self.data, chef, obs, datetime(2026, 12, 2, 7, 40, tzinfo=timezone.utc)), "une seule fois")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
# Usage : python3 outils/generer_donnees_fictives.py data
# Régénère les 6 fichiers JSON fictifs du dossier data/ (graine fixe : résultat identique à chaque fois).
# Ce script ne sert qu'au prototype : plus tard, les agents IA écriront ces fichiers eux-mêmes.
import json, random, math, datetime, os, sys

random.seed(42)
OUT = sys.argv[1]
GEN = "2026-11-01T07:00:00Z"

def meta(source):
    return {"version": 1, "genere_le": GEN, "source": source, "fictif": True}

def clamp(v, a=0, b=100):
    return max(a, min(b, v))

def ecrire(nom, source, donnees, extra=None):
    obj = {"meta": meta(source)}
    if extra:
        obj.update(extra)
    obj["donnees"] = donnees
    with open(os.path.join(OUT, nom), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")

def niveau(n):
    return "attractif" if n >= 65 else ("neutre" if n >= 50 else "defavorable")

# ---------------------------------------------------------------- PAYS
# code, nom, lat, lon, note, verdict, (pib, inflation, per, devise3m, flux Md€)
PAYS = [
 ("US","États-Unis",39.8,-98.6,70,"Croissance robuste et bénéfices solides, mais valorisations tendues.",(2.4,2.9,21.5,1.8,42.0)),
 ("CA","Canada",56.1,-106.3,63,"Économie stable portée par l'énergie, consommation qui s'essouffle.",(1.6,2.4,15.2,-0.6,6.1)),
 ("MX","Mexique",23.6,-102.5,59,"Gagnant de la relocalisation industrielle, risque politique à surveiller.",(2.0,4.1,12.8,0.9,7.4)),
 ("BR","Brésil",-14.2,-51.9,73,"Actions décotées et baisse des taux engagée : le marché profite du cycle des matières premières.",(2.6,3.9,8.4,2.4,6.8)),
 ("AR","Argentine",-38.4,-63.6,41,"Réformes courageuses, mais inflation et devise encore très fragiles.",(1.2,38.0,9.5,-9.8,-1.4)),
 ("GB","Royaume-Uni",54.0,-2.5,57,"Marché décoté et dividendes généreux, croissance faible.",(0.9,3.2,11.9,0.4,2.8)),
 ("FR","France",46.6,2.4,58,"Croissance molle mais valorisations raisonnables et champions mondiaux.",(1.1,2.1,13.8,-0.3,3.4)),
 ("DE","Allemagne",51.2,10.4,52,"Industrie en convalescence, relance budgétaire encore timide.",(0.6,2.3,13.1,-0.3,-0.8)),
 ("CH","Suisse",46.8,8.2,66,"Valeur refuge de qualité, franc fort qui rogne les marges des exportateurs.",(1.3,0.7,17.4,1.2,4.9)),
 ("SA","Arabie saoudite",23.9,45.1,56,"Diversification ambitieuse, dépendance au prix du pétrole encore forte.",(3.1,1.9,16.2,0.0,5.5)),
 ("ZA","Afrique du Sud",-30.6,22.9,44,"Mines attractives, mais réseau électrique et croissance défaillants.",(0.8,4.9,10.3,-3.4,-2.2)),
 ("IN","Inde",20.6,79.0,76,"Moteur de croissance mondial, valorisations élevées mais justifiées.",(6.6,4.0,22.8,-0.8,18.6)),
 ("CN","Chine",35.9,104.2,36,"Déflation, crise immobilière et défiance des investisseurs : prudence maximale.",(3.6,-0.4,10.6,-2.5,-18.0)),
 ("KR","Corée du Sud",35.9,127.8,73,"Cycle des semi-conducteurs très favorable et réforme de la gouvernance en cours.",(2.4,2.0,11.4,1.6,9.8)),
 ("JP","Japon",36.2,138.3,72,"Réformes des entreprises et retour de l'inflation : un marché qui se réveille.",(1.2,2.2,15.6,2.4,13.8)),
 ("AU","Australie",-25.3,133.8,62,"Économie résiliente, dépendante de la demande chinoise en matières premières.",(1.7,3.0,17.0,-1.1,2.6)),
 ("IT","Italie",41.9,12.6,55,"Banques revigorées et dette publique lourde : un marché à dividendes.",(0.7,1.8,11.2,-0.3,2.1)),
 ("ES","Espagne",40.4,-3.7,63,"Croissance parmi les plus fortes d'Europe, portée par le tourisme et les renouvelables.",(2.6,2.6,11.8,-0.3,5.6)),
 ("NL","Pays-Bas",52.1,5.3,64,"Champions technologiques mondiaux dans une économie ouverte et solide.",(1.2,2.9,15.4,-0.3,4.8)),
 ("SE","Suède",60.1,18.6,62,"Industrie de qualité, immobilier encore convalescent.",(1.4,1.6,16.8,1.9,2.4)),
 ("PL","Pologne",51.9,19.1,66,"Rattrapage économique rapide, soutenu par les fonds européens.",(3.2,3.8,9.6,1.4,6.2)),
 ("TW","Taïwan",23.7,121.0,82,"Cœur mondial des semi-conducteurs, porté par la demande liée à l'IA.",(4.8,1.9,18.5,2.1,22.4)),
 ("ID","Indonésie",-2.5,118.0,67,"Démographie porteuse et nickel stratégique pour les batteries.",(5.0,2.4,13.9,-1.0,7.2)),
 ("VN","Vietnam",14.1,108.3,69,"Atelier du monde en plein essor, marché encore peu accessible.",(6.4,3.1,12.6,-0.6,9.1)),
 ("SG","Singapour",1.35,103.8,71,"Place financière de référence en Asie, stabilité exemplaire.",(2.8,2.2,13.2,1.1,8.8)),
 ("TH","Thaïlande",15.9,101.0,52,"Tourisme en reprise, mais consommation et politique fragiles.",(2.0,0.8,14.6,-0.9,-1.5)),
 ("CL","Chili",-35.7,-71.5,58,"Cuivre et lithium en vedette, croissance modeste.",(2.1,3.9,11.4,-1.2,1.9)),
 ("CO","Colombie",4.6,-74.3,48,"Valorisations très basses, incertitudes politiques et budgétaires.",(1.5,5.4,7.6,-2.4,-0.9)),
 ("AE","Émirats arabes unis",23.4,53.8,68,"Hub mondial du commerce et de la finance, diversification réussie.",(3.9,2.1,12.9,0.0,9.6)),
 ("TR","Turquie",39.0,35.2,42,"Désinflation en cours, mais livre fragile et taux très élevés.",(3.0,35.0,6.8,-6.5,1.2)),
 ("EG","Égypte",26.8,30.8,38,"Financements internationaux salutaires, inflation et dette pesantes.",(3.4,24.0,7.2,-5.8,-0.4)),

]

def notes_indic(pib, infl, per, dev, flux, code):
    n_pib = clamp(round(35 + pib * 8))
    n_infl = clamp(round(90 - abs(infl - 2.0) * 16)) if infl < 15 else 8
    n_per = clamp(round(95 - (per - 8) * 3.5))
    n_dev = clamp(round(58 + dev * 5))
    n_flux = clamp(round(55 + flux * 1.1))
    return n_pib, n_infl, n_per, n_dev, n_flux

TEXTES_AGENTS = {
 "US": ("Consommation solide et marché de l'emploi encore tendu ; la banque centrale garde une marge de baisse.",
        "Optimisme élevé chez les investisseurs particuliers, signal de prudence à court terme.",
        "Concentration du marché sur quelques géants technologiques : risque de correction marqué.",
        "Trafic aérien et réservations d'hôtels en hausse de 4 % sur un an : la demande tient."),
 "CA": ("Ralentissement de l'immobilier, mais l'énergie soutient les recettes publiques.",
        "Sentiment neutre, peu de flux spéculatifs.",
        "Ménages très endettés : sensibilité forte aux taux.",
        "Permis de construire en recul de 6 % sur trois mois."),
 "MX": ("Exportations vers les États-Unis au plus haut, investissements industriels en hausse.",
        "Presse financière plutôt positive sur la relocalisation.",
        "Incertitudes sur la réforme judiciaire et les relations commerciales.",
        "Consommation électrique industrielle en hausse de 7 % : les usines tournent."),
 "BR": ("La banque centrale amorce la baisse des taux, l'inflation reflue.",
        "Retour marqué des investisseurs étrangers sur des actions décotées.",
        "Risque budgétaire présent mais contenu.",
        "Récoltes record de soja : soutien aux exportations."),
 "AR": ("Inflation en forte baisse mais encore à deux chiffres élevés.",
        "Regain d'intérêt des fonds spécialisés, sentiment très volatil.",
        "Réserves de change faibles et contrôle des capitaux partiel : risque élevé.",
        "Prix en ligne relevés chaque jour : hausse mensuelle ramenée à 2,5 %."),
 "GB": ("Croissance proche de zéro, inflation des services persistante.",
        "Sentiment déprimé, ce qui laisse de la place à une bonne surprise.",
        "Risque budgétaire modéré, marché obligataire nerveux.",
        "Fréquentation des commerces stable sur un an."),
 "FR": ("Croissance faible, déficit public élevé mais inflation maîtrisée.",
        "Sentiment prudent lié au contexte politique.",
        "Écart de taux avec l'Allemagne à surveiller.",
        "Paiements par carte en hausse de 2 % : consommation stable."),
 "DE": ("Production industrielle en légère reprise, plan d'investissement public en préparation.",
        "Moral des chefs d'entreprise en amélioration depuis trois mois.",
        "Dépendance à la Chine et coût de l'énergie encore élevés.",
        "Trafic des poids lourds sur autoroutes : +1,5 %, reprise timide."),
 "CH": ("Inflation très basse, banque centrale accommodante.",
        "Valeur refuge recherchée en période de tension.",
        "Franc fort : risque de déflation importée.",
        "Exportations horlogères en recul de 3 %."),
 "SA": ("Grands projets d'infrastructure qui soutiennent l'activité non pétrolière.",
        "Sentiment neutre, dépendant du prix du baril.",
        "Volatilité du pétrole et tensions régionales.",
        "Images satellites : chantiers actifs en hausse de 12 %."),
 "ZA": ("Croissance faible freinée par les coupures d'électricité.",
        "Sentiment négatif, les investisseurs étrangers vendent.",
        "Risque social et dette publique en hausse.",
        "Coupures d'électricité : 9 jours sur 30 le mois dernier."),
 "IN": ("Croissance la plus forte des grandes économies, investissement public massif.",
        "Enthousiasme fort des épargnants locaux, flux records vers les fonds actions.",
        "Valorisations élevées : correction possible si les bénéfices déçoivent.",
        "Ventes de deux-roues en hausse de 11 % : la consommation rurale accélère."),
 "CN": ("Déflation persistante, plan de relance jugé insuffisant.",
        "Pessimisme des investisseurs étrangers, rachats d'actions par l'État.",
        "Crise immobilière et tensions commerciales : risque élevé.",
        "Indice de fret portuaire en recul de 5 % sur un mois."),
 "KR": ("Exportations de puces mémoire en forte hausse.",
        "Sentiment positif porté par l'intelligence artificielle.",
        "Exposition forte au cycle électronique mondial.",
        "Exportations des 20 premiers jours : +9 % sur un an."),
 "JP": ("Hausse des salaires et inflation durable : sortie de la déflation.",
        "Intérêt croissant des investisseurs étrangers.",
        "Remontée des taux de la banque centrale : yen volatil.",
        "Fréquentation touristique record, dépenses en hausse de 15 %."),
 "AU": ("Emploi solide, banque centrale prudente.",
        "Sentiment neutre.",
        "Dépendance à la demande chinoise de minerai de fer.",
        "Prix du minerai de fer au port : stables sur un mois."),
 "IT": ("Croissance faible, mais emploi au plus haut historique.", "Sentiment stable, banques plébiscitées.",
        "Dette publique supérieure à 135 % du PIB.", "Fréquentation touristique record cet été."),
 "ES": ("Emploi dynamique et investissements européens en hausse.", "Sentiment positif des investisseurs étrangers.",
        "Chômage des jeunes encore élevé.", "Arrivées de touristes : +8 % sur un an."),
 "NL": ("Économie solide, inflation un peu au-dessus de la moyenne européenne.", "Intérêt marqué pour les valeurs technologiques.",
        "Exposition aux restrictions d'exportation de technologies.", "Trafic du port de Rotterdam stable sur trois mois."),
 "SE": ("Baisse des taux engagée, immobilier qui se stabilise.", "Sentiment neutre.",
        "Endettement immobilier des ménages élevé.", "Commandes industrielles en hausse de 4 %."),
 "PL": ("Croissance robuste soutenue par la consommation et les fonds européens.", "Investisseurs étrangers de retour.",
        "Proximité du conflit en Ukraine.", "Ventes au détail en hausse de 6 % sur un an."),
 "TW": ("Exportations en hausse de 20 % grâce aux puces destinées à l'IA.", "Enthousiasme très fort autour des fondeurs.",
        "Tensions dans le détroit : risque extrême mais jugé peu probable.", "Commandes de serveurs IA : carnets pleins sur 12 mois."),
 "ID": ("Croissance stable autour de 5 %, inflation maîtrisée.", "Sentiment prudent après la volatilité de la roupie.",
        "Interventionnisme de l'État dans certains secteurs.", "Production de nickel en hausse de 12 %."),
 "VN": ("Investissements étrangers records dans l'électronique.", "Enthousiasme des épargnants locaux.",
        "Marché classé « frontière », liquidité limitée.", "Exportations d'électronique : +18 % sur un an."),
 "SG": ("Croissance régulière, rôle de hub régional renforcé.", "Valeur refuge régionale.",
        "Exposition au ralentissement chinois.", "Trafic portuaire record de conteneurs."),
 "TH": ("Croissance molle, légère déflation.", "Sentiment négatif, sorties de capitaux.",
        "Instabilité politique récurrente.", "Arrivées de touristes chinois encore inférieures à 2019."),
 "CL": ("Banque centrale en phase de baisse des taux.", "Sentiment neutre, suspendu au prix du cuivre.",
        "Dépendance aux matières premières.", "Production de lithium en hausse de 15 %."),
 "CO": ("Croissance faible et déficit budgétaire en hausse.", "Pessimisme des investisseurs.",
        "Incertitudes politiques et sécuritaires.", "Ventes de ciment en recul de 5 %."),
 "AE": ("Activité non pétrolière en forte croissance.", "Afflux de capitaux et d'entrepreneurs étrangers.",
        "Exposition aux tensions régionales.", "Transactions immobilières à Dubaï : +20 %."),
 "TR": ("Inflation en reflux mais toujours au-dessus de 30 %.", "Retour prudent de quelques fonds étrangers.",
        "Livre turque fragile : risque de change élevé.", "Prix alimentaires en ligne : +3 % sur un mois."),
 "EG": ("Programme du FMI et investissements du Golfe en soutien.", "Sentiment très prudent.",
        "Dette extérieure et besoins de financement élevés.", "Revenus du canal de Suez encore en baisse de 40 %."),
}

FLUX = [("US","IN",18.4),("US","JP",12.1),("US","MX",8.6),("CN","SA",6.2),("CN","BR",4.8),
        ("CH","US",9.3),("GB","IN",5.1),("JP","US",7.7),("DE","CN",-3.0),("SA","IN",4.0),
        ("FR","US",4.4),("KR","US",5.6),("AU","CN",3.1),("CA","US",6.8),("ZA","GB",2.2),
        ("US","AR",1.6),("TW","US",9.8),("US","TW",6.4),("SG","ID",3.8),("AE","IN",4.6),
        ("NL","US",3.9),("JP","VN",4.2),("KR","VN",3.1),("SA","EG",2.6),("ES","CO",1.2),("DE","PL",3.3)]

def lecture(n, t):
    return {"note": n, "texte": t}

# Code ISO 3166 numérique : identifiant du pays dans data/countries-110m.json
ISO_NUM = {"US":"840","CA":"124","MX":"484","BR":"076","AR":"032","GB":"826","FR":"250","DE":"276","CH":"756",
           "SA":"682","ZA":"710","IN":"356","CN":"156","KR":"410","JP":"392","AU":"036","IT":"380","ES":"724",
           "NL":"528","SE":"752","PL":"616","TW":"158","ID":"360","VN":"704","SG":"702","TH":"764","CL":"152",
           "CO":"170","AE":"784","TR":"792","EG":"818"}

pays = []
for code, nom, lat, lon, note, verdict, (pib, infl, per, dev, flux) in PAYS:
    n = notes_indic(pib, infl, per, dev, flux, code)
    ta = TEXTES_AGENTS[code]
    rnd = lambda d: clamp(note + random.randint(-d, d))
    pays.append({
        "code": code, "iso_num": ISO_NUM[code], "nom": nom, "lat": lat, "lon": lon, "note": note,
        "niveau": niveau(note), "verdict": verdict,
        "indicateurs": {
            "croissance_pib": {"libelle": "Croissance du PIB", "valeur": pib, "unite": "%", "note": n[0]},
            "inflation": {"libelle": "Inflation", "valeur": infl, "unite": "%", "note": n[1]},
            "per": {"libelle": "Valorisation (PER)", "valeur": per, "unite": "x", "note": n[2]},
            "devise_3m": {"libelle": "Devise sur 3 mois", "valeur": dev, "unite": "%", "note": n[3]},
            "flux_etrangers": {"libelle": "Flux étrangers", "valeur": flux, "unite": "Md€", "note": n[4]},
        },
        "lectures_agents": {
            "macro": lecture(clamp(round((n[0] + n[1]) / 2 + random.randint(-4, 4))), ta[0]),
            "sentiment": lecture(rnd(10), ta[1]),
            "risque": lecture(rnd(12), ta[2]),
            "donnees_alternatives": lecture(rnd(8), ta[3]),
        },
        # Flux de capitaux sortants (montant en milliards de dollars sur la période)
        "flux": [{"vers": b, "montant_md": m, "devise": "USD", "periode": "1 mois"} for a, b, m in FLUX if a == code],
    })

# ---------------------------------------------------------------- SECTEURS & ENTREPRISES
# Pour chaque pays : 3 secteurs (nom, capitalisation Md€, momentum 3 mois %) et noms inventés.
SECT = {
 "US": [("Technologie",14800,6.8,["Nexora Systems","Quantix Labs","Helion Cloud"]),
        ("Santé",5200,-1.4,["Vitalis Therapeutics","Meridian Health"]),
        ("Énergie",2600,2.1,["Prairie Fuel","Blue Mesa Energy"])],
 "CA": [("Énergie",420,3.4,["Northfield Oil","Glacier Gas"]),
        ("Banques",510,1.2,["Maple Trust","Laurentide Bank"]),
        ("Mines",210,7.9,["Boreal Gold","Yukon Metals"])],
 "MX": [("Industrie",95,5.6,["Grupo Rivera Industrial","Monterrey Aceros"]),
        ("Consommation",120,-0.8,["Alimentos Sol","Tiendas Paloma"]),
        ("Banques",88,2.3,["Banco Azteca Norte","Finanzas del Valle"])],
 "BR": [("Matières premières",160,4.6,["Vale Verde Minério","Ferro Paulista"]),
        ("Banques",140,2.1,["Banco Ipê","Itaú Cerrado"]),
        ("Énergie",110,3.2,["Petro Atlântico","Energia Tropical"])],
 "AR": [("Énergie",28,9.4,["Vaca Muerta Energía","Andes Petróleo"]),
        ("Banques",19,-4.2,["Banco Pampa","Crédito del Plata"]),
        ("Agroalimentaire",14,-1.9,["Agro Patagonia","Granos del Sur"])],
 "GB": [("Énergie",310,0.9,["Thames Petroleum","Brightwater Energy"]),
        ("Banques",280,3.1,["Albion Bank","Crownstone Finance"]),
        ("Consommation",350,-1.1,["Kingsway Brands","Harrowgate Foods"])],
 "FR": [("Luxe",620,4.2,["Maison Aurèle","Lumen Paris","Atelier Vernet"]),
        ("Industrie",340,1.6,["Aérosud","Groupe Valmont"]),
        ("Banques",190,-0.9,["Banque Hexagone","Crédit Rivage"])],
 "DE": [("Automobile",240,-5.3,["Rheinwagen","Bavaria Motorwerke"]),
        ("Industrie",410,2.4,["Kessler Technik","Nordstahl"]),
        ("Logiciels",290,5.1,["Datenwerk","Logikon"])],
 "CH": [("Pharmacie",720,1.1,["Helvetia Pharma","Alpina Biotech"]),
        ("Agroalimentaire",310,-0.6,["Lacustra Foods","Cimes Nutrition"]),
        ("Banques",160,3.8,["Banque Léman","Gotthard Capital"])],
 "SA": [("Pétrole",1650,-1.2,["Arabian Crude Co.","Najd Energy"]),
        ("Banques",240,2.6,["Riyad Al Noor Bank","Banque du Golfe"]),
        ("Pétrochimie",130,-3.4,["Desert Polymers","Jubail Chimie"])],
 "ZA": [("Mines",180,8.2,["Highveld Platinum","Karoo Gold"]),
        ("Banques",75,-1.7,["Cape Capital","Ubuntu Bank"]),
        ("Télécoms",42,-4.6,["Savanna Telecom","Zulu Mobile"])],
 "IN": [("Technologie",520,3.9,["Infonova Services","Deccan Digital","Ganga Soft"]),
        ("Banques",610,4.7,["Bharat Prime Bank","Kaveri Finance"]),
        ("Consommation",380,2.2,["Saffron Brands","Monsoon Motors"])],
 "CN": [("Technologie",1900,-6.2,["Longhua Tech","Pearl River Digital"]),
        ("Immobilier",210,-11.5,["Jade Tower Properties","Huaxin Habitat"]),
        ("Véhicules électriques",480,-1.2,["Dragon Volt","Sino E-Drive"])],
 "KR": [("Semi-conducteurs",620,11.2,["Hanbit Semicon","Seoul Memory"]),
        ("Automobile",130,3.1,["Daehan Motors","Busan Mobility"]),
        ("Chimie & batteries",150,-1.2,["Korea Cell","Hwasan Chemical"])],
 "JP": [("Industrie",880,5.9,["Kanto Robotics","Shinkai Heavy"]),
        ("Automobile",520,2.7,["Sakura Motors","Hokuto Auto"]),
        ("Banques",360,7.2,["Mizuki Financial","Edo Trust Bank"])],
 "AU": [("Mines",410,-0.4,["Pilbara Iron","Outback Lithium"]),
        ("Banques",480,1.9,["Southern Cross Bank","Harbour Finance"]),
        ("Santé",150,3.3,["Coral Health","Eucalyptus Bio"])],
 "IT": [("Banques",210,5.2,["Banca Tevere","Credito Lombardo"]),
        ("Énergie",140,0.8,["Adriatica Energia","Sole Rinnovabili"]),
        ("Luxe",120,2.6,["Casa Veronelli","Moda Arno"])],
 "ES": [("Banques",190,4.1,["Banco Meseta","Caja Levante"]),
        ("Renouvelables",110,3.0,["Viento Ibérico","Sol de Castilla"]),
        ("Tourisme",60,6.2,["Hoteles Costa Brava","Viajes Alhambra"])],
 "NL": [("Semi-conducteurs",420,3.6,["Lithovia","Polder Photonics"]),
        ("Consommation",150,-1.0,["Tulipa Foods","Delta Brands"]),
        ("Paiements",70,2.1,["Grachten Pay","Oranje Ledger"])],
 "SE": [("Industrie",260,3.2,["Nordkraft Verktyg","Vasa Maskin"]),
        ("Banques",120,1.1,["Svea Nordbank","Gotland Finans"]),
        ("Immobilier",40,-3.1,["Mälar Fastigheter","Norrhus"])],
 "PL": [("Banques",75,5.8,["Bank Wisła","Kredyt Mazowsze"]),
        ("Commerce en ligne",30,7.4,["Bursztyn Market","Polska Paczka"]),
        ("Énergie",25,-0.6,["Wisła Nowa Energia","Tatra Power"])],
 "TW": [("Semi-conducteurs",1350,12.4,["Formosa Silicon","Hsinchu Wafer Works","Jade Mountain Chips"]),
        ("Électronique",260,6.1,["Taipei Assembly","Keelung Circuits"]),
        ("Banques",110,1.8,["Formosa Trust","Pacific Harbour Bank"])],
 "ID": [("Banques",180,-1.5,["Bank Nusantara","Jakarta Raya Finance"]),
        ("Mines & nickel",60,4.8,["Sulawesi Nickel","Borneo Mining"]),
        ("Consommation",70,0.6,["Garuda Foods","Batik Retail"])],
 "VN": [("Électronique",35,9.1,["Saigon Electronics","Mekong Devices"]),
        ("Banques",55,4.0,["Hanoi Commercial Bank","Lotus Bank"]),
        ("Immobilier",25,-2.5,["Ha Long Land","Red River Homes"])],
 "SG": [("Banques",220,3.4,["Merlion Bank","Straits Capital"]),
        ("Immobilier",60,0.4,["Marina Reit","Orchard Properties"]),
        ("Logistique",40,2.9,["Lion City Logistics","Sentosa Shipping"])],
 "TH": [("Tourisme",30,2.4,["Siam Resorts","Andaman Hotels"]),
        ("Banques",45,-1.8,["Bank of Chao Phraya","Krung Finance"]),
        ("Énergie",40,-2.6,["Thai Gulf Energy","Isan Power"])],
 "CL": [("Mines",70,4.6,["Atacama Cobre","Andes Litio"]),
        ("Banques",35,1.2,["Banco Pacífico Sur","Valparaíso Crédito"]),
        ("Distribution",20,-1.4,["Mercado Austral","Tiendas Maipo"])],
 "CO": [("Énergie",45,-3.6,["Petro Andina","Llanos Energía"]),
        ("Banques",30,-1.0,["Banco Cafetero","Bogotá Capital"]),
        ("Ciment",8,-4.8,["Cementos Magdalena","Concreto Caribe"])],
 "AE": [("Immobilier",90,8.4,["Dune Estates","Marina Crest"]),
        ("Banques",160,3.0,["Emirates Pearl Bank","Abu Dhabi Horizon"]),
        ("Logistique",50,4.2,["Falcon Logistics","Gulf Gateway"])],
 "TR": [("Banques",35,6.5,["Bosphorus Bank","Anatolia Kredi"]),
        ("Industrie",30,-2.0,["Ege Sanayi","Kapadokya Makina"]),
        ("Distribution",20,1.0,["Bazaar Market","Istanbul Retail"])],
 "EG": [("Banques",18,2.2,["Nile Commercial Bank","Delta Finance"]),
        ("Immobilier",9,-3.0,["Giza Developments","Alexandria Homes"]),
        ("Télécoms",6,-1.2,["Sphinx Telecom","Pharaon Mobile"])],
}

def tick(nom, pris):
    base = "".join(c for c in nom.upper() if c.isalpha() and c.isascii())[:4]
    t, i = base, 1
    while t in pris:
        t = base[:3] + str(i); i += 1
    pris.add(t)
    return t

secteurs, entreprises, tickers = [], [], set()
for code, liste in SECT.items():
    note_pays = next(p for p in pays if p["code"] == code)["note"]
    for nom_s, cap, mom, noms in liste:
        sid = f"{code}-{nom_s.lower().replace(' ', '-').replace('&', 'et').replace('é','e').replace('è','e').replace('--','-')}"
        note_s = clamp(round(note_pays + mom * 1.6 + random.randint(-4, 4)))
        ents = []
        poids = [random.uniform(0.6, 1.4) for _ in noms]
        tot = sum(poids)
        for nom_e, pw in zip(noms, poids):
            t = tick(nom_e, tickers)
            biais = random.randint(-14, 14)
            ca = round(mom * 0.8 + random.uniform(-3, 9) + biais / 6, 1)
            ben = round(ca * random.uniform(0.8, 2.2) + random.uniform(-6, 4), 1)
            marge = round(random.uniform(5, 32) + (8 if "Luxe" in nom_s or "Logiciel" in nom_s or "Technologie" in nom_s else 0), 1)
            dette = round(max(-0.8, random.uniform(-0.5, 3.8) - biais / 20), 1)
            per_rel = round(random.uniform(-35, 40) - biais, 0)
            notes = {
                "croissance_ca": clamp(round(45 + ca * 4)),
                "benefice": clamp(round(48 + ben * 2.5)),
                "marge": clamp(round(30 + marge * 1.8)),
                "dette_ebitda": clamp(round(88 - dette * 15)),
                "per_vs_secteur": clamp(round(60 - per_rel * 0.7)),
            }
            note_e = clamp(round(sum(notes.values()) / 5 * 0.7 + note_s * 0.3))
            cap_e = round(cap * pw / tot)
            e = {
                "ticker": t, "nom": nom_e, "secteur": sid, "pays": code,
                "capitalisation_md": cap_e, "note": note_e, "niveau": niveau(note_e),
                "verdict": None,
                "indicateurs": {
                    "croissance_ca": {"libelle": "Croissance du CA", "valeur": ca, "unite": "%", "note": notes["croissance_ca"]},
                    "benefice": {"libelle": "Bénéfice (évol. 1 an)", "valeur": ben, "unite": "%", "note": notes["benefice"]},
                    "marge": {"libelle": "Marge opérationnelle", "valeur": marge, "unite": "%", "note": notes["marge"]},
                    "dette_ebitda": {"libelle": "Dette nette / EBITDA", "valeur": dette, "unite": "x", "note": notes["dette_ebitda"]},
                    "per_vs_secteur": {"libelle": "PER vs secteur", "valeur": per_rel, "unite": "%", "note": notes["per_vs_secteur"]},
                },
            }
            # Verdict de l'agent entreprises
            if note_e >= 65:
                e["verdict"] = f"Dossier attractif : {'croissance soutenue' if ca > 5 else 'rentabilité solide'}{', bilan sain' if dette < 1.5 else ', bilan correct' if dette < 3 else ' malgré une dette élevée'}. Renforcement possible."
            elif note_e >= 50:
                e["verdict"] = f"Dossier équilibré : {'valorisation exigeante' if per_rel > 10 else 'valorisation correcte'}, à conserver sans renforcer."
            else:
                e["verdict"] = f"Dossier fragile : {'endettement élevé' if dette > 2.5 else 'croissance en panne'}. Prudence recommandée."
            mac = clamp(note_pays + random.randint(-6, 6))
            sen = clamp(note_e + random.randint(-12, 12))
            ris = clamp(round(70 - dette * 10 + random.randint(-8, 8)))
            alt = clamp(note_e + random.randint(-10, 10))
            e["agents"] = {
                "entreprises": {"note": note_e, "texte": e["verdict"]},
                "macro": {"note": mac, "texte": f"L'environnement de {next(p['nom'] for p in pays if p['code']==code)} est {niveau(mac).replace('defavorable','défavorable')} pour le secteur {nom_s.lower()} : {'la demande intérieure soutient l’activité' if mac>=60 else 'la conjoncture limite le potentiel'}."},
                "sentiment": {"note": sen, "texte": f"{'Les analystes relèvent leurs objectifs' if sen>=60 else 'Les analystes restent partagés' if sen>=50 else 'Les révisions de bénéfices sont orientées à la baisse'} ; tonalité des médias {'positive' if sen>=60 else 'neutre' if sen>=50 else 'négative'} sur 30 jours."},
                "risque": {"note": ris, "texte": f"Volatilité {'faible' if ris>=65 else 'moyenne' if ris>=50 else 'élevée'}, dette nette à {str(dette).replace('.', ',')} fois l'EBITDA. {'Bilan robuste.' if ris>=65 else 'Point de vigilance sur le refinancement.' if ris<50 else 'Profil de risque acceptable.'}"},
                "donnees_alternatives": {"note": alt, "texte": f"{'Recherches en ligne sur la marque en hausse' if alt>=60 else 'Recherches en ligne stables' if alt>=50 else 'Recherches en ligne en recul'} ({random.randint(-15, 25):+d} % sur 3 mois), avis clients {'favorables' if alt>=55 else 'mitigés'}."},
            }
            v = lambda x: str(x).replace(".", ",")
            e["etude_complete"] = [
                {"titre": "Thèse d'investissement", "texte": f"{nom_e} est un acteur du secteur {nom_s.lower()} ({next(p['nom'] for p in pays if p['code']==code)}) pesant environ {cap_e} Md€ en Bourse. Note globale de {note_e}/100. {e['verdict']}"},
                {"titre": "Activité et positionnement", "texte": f"Le chiffre d'affaires progresse de {v(ca)} % sur un an. Le groupe {'gagne des parts de marché' if ca>4 else 'défend ses positions' if ca>0 else 'perd du terrain face à ses concurrents'} dans un secteur dont le momentum sur 3 mois est de {v(mom)} %."},
                {"titre": "Analyse financière", "texte": f"La marge opérationnelle atteint {v(marge)} % et le bénéfice évolue de {v(ben)} % sur un an. La dette nette représente {v(dette)} fois l'EBITDA, {'un niveau confortable' if dette<1.5 else 'un niveau à surveiller' if dette<3 else 'un niveau élevé'}."},
                {"titre": "Valorisation", "texte": f"Le PER est {'supérieur' if per_rel>0 else 'inférieur'} de {v(abs(per_rel))} % à la moyenne du secteur. {'Le marché paie déjà une partie de la croissance future.' if per_rel>10 else 'La valorisation laisse un potentiel de revalorisation.' if per_rel<-10 else 'La valorisation est en ligne avec les pairs.'}"},
                {"titre": "Risques principaux", "texte": "Ralentissement de la demande mondiale, évolution défavorable des devises, pression réglementaire et concurrence accrue sur les prix."},
                {"titre": "Conclusion des agents", "texte": f"Synthèse du chef d'orchestre : {'surpondérer' if note_e>=65 else 'conserver' if note_e>=50 else 'sous-pondérer'}. Horizon de 12 mois. Analyse purement fictive, ne constitue pas un conseil."},
            ]
            entreprises.append(e)
            ents.append(t)
        secteurs.append({"id": sid, "pays": code, "nom": nom_s, "capitalisation_md": cap,
                         "momentum_3m": mom, "note": note_s, "niveau": niveau(note_s), "entreprises": ents})

ecrire("secteurs.json", "fictif (futur : agent-pays)", secteurs)

# Momentum boursier du pays : moyenne des momentums sectoriels pondérée par la capitalisation
for p in pays:
    sp = [x for x in secteurs if x["pays"] == p["code"]]
    mom = round(sum(x["capitalisation_md"] * x["momentum_3m"] for x in sp) / sum(x["capitalisation_md"] for x in sp), 1)
    p["momentum_boursier"] = {"libelle": "Momentum boursier 3 mois", "valeur": mom, "unite": "%", "note": clamp(round(55 + mom * 4))}
ecrire("pays.json", "fictif (futur : agent-pays + agent-macro)", pays)
ecrire("entreprises.json", "fictif (futur : agent-entreprises)", entreprises)

# ---------------------------------------------------------------- ALERTES
alertes = [
 {"id": "a1", "heure": "06:15", "agent": "macro", "pays": "IN", "niveau": "attractif",
  "titre": "Inde : PIB trimestriel au-dessus des attentes",
  "texte": "Croissance de 6,6 % sur un an, portée par l'investissement public. Note pays relevée à 76/100."},
 {"id": "a2", "heure": "07:42", "agent": "risque", "pays": "CN", "niveau": "defavorable",
  "titre": "Chine : nouveau défaut d'un promoteur immobilier",
  "texte": "Le secteur immobilier chute de 11,5 % sur 3 mois. Exposition à réduire sur les valeurs liées."},
 {"id": "a3", "heure": "08:30", "agent": "sentiment", "pays": "US", "niveau": "neutre",
  "titre": "États-Unis : euphorie des particuliers sur la tech",
  "texte": "L'indice de sentiment atteint un sommet sur 12 mois, historiquement suivi de consolidations."},
 {"id": "a4", "heure": "09:05", "agent": "donnees_alternatives", "pays": "AR", "niveau": "defavorable",
  "titre": "Argentine : les prix en ligne repartent à la hausse",
  "texte": "Le relevé quotidien des prix montre +2,5 % sur un mois. Le peso reste sous pression."},
]
ecrire("alertes.json", "fictif (futur : agent-chef-orchestre)", alertes)

# ---------------------------------------------------------------- MARCHÉS
marches = [
 ("indices","S&P 500",6412.8,0.34,"pts"),("indices","CAC 40",7512.3,-0.42,"pts"),
 ("indices","DAX",19870.5,0.12,"pts"),("indices","Nikkei 225",41250.0,1.08,"pts"),
 ("indices","MSCI World",3985.2,0.21,"pts"),("indices","Sensex",84120.6,0.66,"pts"),
 ("taux","OAT 10 ans",3.18,0.03,"%"),("taux","Bund 10 ans",2.54,0.02,"%"),
 ("taux","US 10 ans",4.21,-0.04,"%"),
 ("devises","EUR/USD",1.0912,0.15,""),("devises","USD/JPY",148.36,-0.22,""),
 ("devises","EUR/CHF",0.9384,-0.08,""),
 ("matieres_premieres","Brent",78.40,-1.12,"$"),("matieres_premieres","Or",2684.5,0.48,"$"),
 ("matieres_premieres","Cuivre",9420.0,0.91,"$"),("matieres_premieres","Gaz TTF",36.8,2.35,"€"),
]
ecrire("marches.json", "fictif (futur : agent-macro)",
       [{"categorie": c, "nom": n, "valeur": v, "variation": d, "unite": u} for c, n, v, d, u in marches])

# ---------------------------------------------------------------- PORTEFEUILLE
debut = datetime.date(2026, 1, 2)
hist, p, m = [], 100000.0, 100000.0
rend_p, rend_m = [], []
for s in range(44):
    d = debut + datetime.timedelta(weeks=s)
    if s > 0:
        rm = random.gauss(0.0042, 0.016)
        rp = rm * 0.8 + random.gauss(0.0016, 0.006)
        if 13 <= s <= 16:  # correction de printemps
            rm -= 0.022; rp -= 0.017
        m *= 1 + rm; p *= 1 + rp
        rend_p.append(rp); rend_m.append(rm)
    hist.append({"date": d.isoformat(), "portefeuille": round(p), "msci_world": round(m)})

def sharpe(r, rf=0.025 / 52):
    moy = sum(r) / len(r); ec = math.sqrt(sum((x - moy) ** 2 for x in r) / (len(r) - 1))
    return round((moy - rf) / ec * math.sqrt(52), 2)

def perte_max(serie):
    pic, pm = serie[0], 0
    for v in serie:
        pic = max(pic, v); pm = min(pm, v / pic - 1)
    return round(pm * 100, 1)

valeur = hist[-1]["portefeuille"]
positions = [
 ("ETF MSCI World", "coeur", 40, 9.1), ("ETF S&P 500", "coeur", 15, 11.4),
 ("ETF Obligations euro", "coeur", 15, 2.3), ("ETF Inde", "satellite", 8, 14.6),
 ("ETF Japon", "satellite", 7, 12.2), ("Maison Aurèle", "satellite", 5, -3.8, "MAIS"),
 ("Hanbit Semicon", "satellite", 5, 27.5, "HANB"), ("Liquidités", "satellite", 5, 0.0),
]
positions = [x if len(x) == 5 else x + (None,) for x in positions]
portefeuille = {
    "capital_initial": 100000, "valeur_actuelle": valeur, "devise": "EUR",
    "date_debut": debut.isoformat(),
    "statistiques": {
        "performance_totale": round((valeur / 100000 - 1) * 100, 2),
        "performance_msci_world": round((hist[-1]["msci_world"] / 100000 - 1) * 100, 2),
        "sharpe": sharpe(rend_p), "sharpe_msci_world": sharpe(rend_m),
        "perte_max": perte_max([h["portefeuille"] for h in hist]),
        "perte_max_msci_world": perte_max([h["msci_world"] for h in hist]),
    },
    "allocation": {"coeur": 70, "satellite": 30},
    "positions": [{"nom": n, "ticker": tk, "poche": pc, "poids": w, "valeur": round(valeur * w / 100), "performance": pf} for n, pc, w, pf, tk in positions],
    "historique": hist,
    "derniere_decision": {
        "date": "2026-10-30", "heure": "17:45", "agent": "trader", "action": "Renforcement",
        "titre": "Renforcement de la poche Inde (+2 %)",
        "texte": "Suite à l'alerte macro sur le PIB indien, l'agent trader fictif renforce l'ETF Inde de 2 points, financés par les liquidités. Taille limitée par l'agent risque en raison des valorisations élevées.",
    },
}
with open(os.path.join(OUT, "portefeuille.json"), "w", encoding="utf-8") as f:
    json.dump({"meta": meta("fictif (futur : agent-trader)"), "donnees": portefeuille}, f, ensure_ascii=False, indent=2)
    f.write("\n")
print(len(pays), "pays,", len(secteurs), "secteurs,", len(entreprises), "entreprises,",
      "portefeuille", valeur, portefeuille["statistiques"])

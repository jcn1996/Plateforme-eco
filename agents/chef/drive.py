"""
Dépôt facultatif du briefing dans un dossier Google Drive (compte de service Google).

Secrets : GOOGLE_SERVICE_ACCOUNT_JSON (contenu JSON de la clé du compte de service) et DRIVE_FOLDER_ID
(identifiant du dossier, partagé avec l'adresse du compte de service en tant qu'éditeur).
Sans ces secrets, le dépôt est ignoré (source « non configurée » dans l'écran Santé).
La bibliothèque google-auth n'est installée par le workflow que si le secret existe.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

URL_ENVOI = "https://www.googleapis.com/upload/drive/v3/files"
URL_FICHIERS = "https://www.googleapis.com/drive/v3/files"


def configure() -> bool:
    return bool(os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON") and os.environ.get("DRIVE_FOLDER_ID"))


def deposer(chemins: list[Path]) -> dict:
    """Envoie (ou remplace) chaque fichier dans le dossier. Renvoie {etat, detail}."""
    if not configure():
        return {"etat": "non configurée", "detail": "secrets GOOGLE_SERVICE_ACCOUNT_JSON et DRIVE_FOLDER_ID absents : dépôt ignoré"}
    try:
        from google.auth.transport.requests import AuthorizedSession
        from google.oauth2 import service_account
    except ImportError:
        return {"etat": "échec", "detail": "bibliothèque google-auth absente"}
    try:
        info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"])
        cred = service_account.Credentials.from_service_account_info(info, scopes=["https://www.googleapis.com/auth/drive.file"])
        s = AuthorizedSession(cred)
        dossier = os.environ["DRIVE_FOLDER_ID"]
        envoyes = []
        for chemin in chemins:
            nom = chemin.name
            mime = "text/markdown" if nom.endswith(".md") else "application/json"
            q = f"name = '{nom}' and '{dossier}' in parents and trashed = false"
            r = s.get(URL_FICHIERS, params={"q": q, "fields": "files(id)", "supportsAllDrives": "true", "includeItemsFromAllDrives": "true"}, timeout=60)
            r.raise_for_status()
            existants = r.json().get("files") or []
            contenu = chemin.read_bytes()
            if existants:
                r = s.patch(f"{URL_ENVOI}/{existants[0]['id']}", params={"uploadType": "media", "supportsAllDrives": "true"},
                            data=contenu, headers={"Content-Type": mime}, timeout=60)
            else:
                limite = "limite-chef-orchestre"
                corps = (f"--{limite}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
                         + json.dumps({"name": nom, "parents": [dossier]}) + f"\r\n--{limite}\r\nContent-Type: {mime}\r\n\r\n").encode() + contenu + f"\r\n--{limite}--".encode()
                r = s.post(URL_ENVOI, params={"uploadType": "multipart", "supportsAllDrives": "true"}, data=corps,
                           headers={"Content-Type": f"multipart/related; boundary={limite}"}, timeout=60)
            r.raise_for_status()
            envoyes.append(nom)
        return {"etat": "ok", "detail": f"déposé : {', '.join(envoyes)}"}
    except Exception as e:  # noqa: BLE001
        return {"etat": "échec", "detail": str(e)[:200]}

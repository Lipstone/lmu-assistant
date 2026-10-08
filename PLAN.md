# Plan : LMU Assistant

## Objectif

Rendre visibles, en course et hors course, les données utiles du jeu **Le Mans Ultimate** (LMU), sur deux supports alimentés par une seule source :

1. un **overlay** par-dessus le jeu ;
2. une **page web locale** (PC, tablette, téléphone sur le réseau local).

Les fonctionnalités sont listées dans [FEATURES.md](FEATURES.md) et ajoutées une par une.

## Architecture

```
 Le Mans Ultimate (Windows)
   │  mémoire partagée (télémétrie + scoring)      API REST locale du jeu (optionnelle)
   ▼                                               ▼
 ┌──────────────────────────── backend Python ────────────────────────────┐
 │ sources/        lit les données brutes  →  Snapshot (modèle commun)   │
 │ calculs/        carburant, énergie, delta, moyennes, stints…          │
 │ stockage/       SQLite : tours, relais, sessions (hors course)        │
 │ serveur         FastAPI : HTTP (pages, API) + WebSocket /ws (~10 Hz)  │
 └────────────────────────────────────────────────────────────────────────┘
   │ WebSocket JSON                     │ WebSocket JSON
   ▼                                    ▼
 Page web locale (navigateur)        Overlay (fenêtre transparente pywebview)
 http://<pc>:8765/                   http://localhost:8765/?mode=overlay
```

Un seul code d'affichage : les widgets sont des composants web. L'overlay ouvre une fenêtre transparente, sans bordure et toujours au premier plan par widget ; chacune charge la page en `mode=overlay&widget=<id>` (fond transparent, un seul widget compact) et se place sur l'écran selon la configuration.

## Exigences obligatoires

- **Lancement par un exécutable** : l'application se lance en double-cliquant sur `LMU-Assistant.exe` (Windows), sans installer Python. L'exécutable démarre le serveur et l'overlay ensemble ; il est construit avec PyInstaller par la CI à chaque modification (artefact téléchargeable dans GitHub Actions). Toute nouvelle fonctionnalité doit rester compatible avec ce mode (fichiers web embarqués, données dans `data/` à côté de l'exe).

## Choix techniques (par défaut, modifiables)

| Sujet | Choix | Pourquoi |
|---|---|---|
| Backend | Python 3.11+, FastAPI, uvicorn | Lecture mémoire partagée simple avec `mmap` + `ctypes`, serveur WebSocket léger |
| Front | HTML/CSS/JS sans framework ni build | Démarrage immédiat ; on passera à un framework si les widgets se multiplient |
| Overlay | pywebview (WebView2 sous Windows) | Réutilise les widgets web ; alternative : source navigateur OBS pour le streaming |
| Exécutable | PyInstaller (un seul fichier, console affichant les adresses) | Lancement en double-clic, sans Python installé |
| Stockage | SQLite | Historique des tours et relais pour l'analyse hors course, zéro installation |

## Données du jeu

LMU tourne sur le moteur de rFactor 2. Deux sources sont prévues, à confirmer sur la version installée du jeu :

1. **Mémoire partagée** (principale, haute fréquence) : télémétrie du véhicule (vitesse, régime, pédales, carburant, pneus, freins) et scoring (positions, écarts, tours, drapeaux, météo). Selon la version, via l'interface native de LMU ou via le plugin rFactor 2 *rF2SharedMemoryMapPlugin*. La structure exacte sera documentée dans `docs/donnees-lmu.md` au moment de l'implémentation.
2. **API REST locale du jeu** (secondaire, basse fréquence) : infos de session et de stratégie non présentes en mémoire partagée (par exemple énergie virtuelle ou réglages de stand selon la version). À valider.

Chaque source produit le même `Snapshot` (voir `backend/lmu_assistant/model.py`), ce qui permet de développer et tester avec la source `mock` sans lancer le jeu.

## Étapes

| # | Étape | Contenu | État |
|---|---|---|---|
| 0 | Squelette | Serveur FastAPI + WebSocket, source simulée, page web, overlay | ✅ fait |
| 1 | Lecture LMU | Source `lmu` : mémoire partagée → `Snapshot`, doc des champs | à faire |
| 2 | Premiers widgets course | Carburant, delta, temps au tour, pneus (F01 à F05) | en cours (F01 à F05 faits) |
| 3 | Overlay configurable | Choix des widgets, positions, taille, opacité, raccourci afficher/masquer | à faire |
| 4 | Historique | Enregistrement SQLite des tours et relais | à faire |
| 5 | Hors course | Analyse des relais, stratégie, rapport de session | à faire |
| 6 | Exécutable | `LMU-Assistant.exe` (serveur + overlay), construit par la CI | ✅ fait |

Après l'étape 1, chaque fonctionnalité de FEATURES.md est ajoutée à la demande, avec son widget web et sa variante overlay.

## Conventions

- Une fonctionnalité = un identifiant `Fxx` dans FEATURES.md, une branche, une PR.
- Les calculs (conso moyenne, tours restants…) vivent côté backend et sont testés avec des données enregistrées ; le front n'affiche que des valeurs prêtes.
- Le message WebSocket est un JSON `{ "type": "snapshot", "data": {...} }` ; les champs ajoutés restent rétrocompatibles.

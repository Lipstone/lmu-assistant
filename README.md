# LMU Assistant

Assistant « ingénieur augmenté » pour **Le Mans Ultimate** : les données simples utiles en course (carburant, énergie, delta, pneus…) façon outils type *Go Fast*, et des éléments hors course (stints, stratégie, analyse) qu'on ne voit pas dans le jeu.

Tout est affichable de deux façons, à partir des mêmes données :

- **Page web locale** : `http://localhost:8765`, sur le PC, une tablette ou un téléphone du réseau local.
- **Overlay en jeu** : une fenêtre transparente, sans bordure et toujours au premier plan qui affiche les mêmes widgets (jeu en mode *fenêtré sans bordure*).

> État : squelette. Le serveur tourne avec une source de données **simulée** (`mock`) pour développer sans le jeu, ou avec la lecture réelle de LMU (`lmu`, à valider en jeu, voir [docs/donnees-lmu.md](docs/donnees-lmu.md)).

## Lancer l'application

Double-cliquer sur **`LMU-Assistant.exe`** (Windows, sans installer Python). Il démarre le serveur et l'overlay ensemble ; la console affiche les adresses de la page web (PC et réseau local). Fermer l'overlay ou la console arrête tout.

- Télécharger l'exe : onglet **Actions** du dépôt → dernier passage de la CI sur `main` → artefact **LMU-Assistant-windows**.
- Options utiles : `LMU-Assistant.exe --no-overlay` (page web seulement), `--browser` (ouvre aussi la page), `--source mock` (données simulées), et toutes les options du serveur ci-dessous.
- Les réglages et enregistrements sont dans le dossier `data/` créé à côté de l'exe.

Construire l'exe soi-même (sous Windows) :

```bash
pip install -e ".[overlay,build]"
python packaging/build_exe.py      # → dist/LMU-Assistant.exe
```

## Développement

Prérequis : Python 3.11+ (Windows pour la lecture réelle du jeu, n'importe quel OS pour le mode simulé).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS : source .venv/bin/activate)
pip install -e .

# Serveur + page web (données simulées)
python -m lmu_assistant --source mock
# puis ouvrir http://localhost:8765

# Serveur + overlay en une commande (comme l'exe)
pip install -e ".[overlay]"
lmu-assistant --source mock

# Overlay seul (dans un 2e terminal, serveur lancé)
python overlay/overlay.py
```

`--source lmu` (par défaut) lit la mémoire partagée native du jeu sous Windows, sans plugin à installer : voir [docs/donnees-lmu.md](docs/donnees-lmu.md).

## Carburant (F01)

Le widget **Carburant** affiche le niveau, la conso du dernier tour et la moyenne des 5 derniers tours valides (nombre de tours entre parenthèses), les tours possibles avec le carburant à bord, les tours restant jusqu'à l'arrivée et le **carburant à ajouter pour finir** (« assez » s'il n'en manque pas). Les calculs sont faits côté serveur (`backend/lmu_assistant/fuel.py`), donc identiques sur la page web, la tablette et l'overlay.

- Un tour compte dans la moyenne s'il a été suivi depuis la ligne, sans passage aux stands ni ravitaillement. La moyenne repart de zéro quand la session, la piste ou la voiture change.
- Course chronométrée : à la fin du temps on finit le tour en cours, l'estimation arrondit donc au passage de ligne suivant (avec le temps au tour moyen). Course au nombre de tours : tours restants d'après `mMaxLaps`.
- Pas de marge de sécurité ajoutée : le chiffre « À ajouter » est le strict nécessaire.

## Réglages de l'overlay

- Page **Réglages overlay** (lien dans la barre du haut, ou `http://localhost:8765/settings.html`) : widgets affichés, position (pixels dans la fenêtre overlay), échelle, opacité et **transparence du fond** (globales ou par widget), position/taille de la fenêtre, clics traversants et raccourci. « Enregistrer » applique tout de suite aux pages ouvertes ; l'overlay relit la fenêtre et le raccourci sous ~2 s.
- **Transparence** : « Opacité » rend tout le widget transparent (texte compris) ; « Fond » ne touche que le fond (0 = chiffres posés directement sur l'image du jeu). Les colonnes Opacité/Fond d'un widget remplacent les valeurs globales ; laisser vide pour garder la valeur globale.
- Sur la page normale, seule la visibilité des widgets s'applique (grille automatique).
- Raccourci global **afficher/masquer** : `ctrl+shift+o` par défaut (paquet `keyboard`, inclus dans l'exe et dans `pip install -e ".[overlay]"` sous Windows ; sans lui l'overlay marche, sans raccourci).
- **Clics traversants** (Windows, activé par défaut) : les clics passent au jeu, donc la fenêtre ne se déplace plus à la souris ; la placer depuis la page de réglages, ou lancer `python overlay/overlay.py --no-click-through` pour la déplacer à la main.
- Les réglages sont dans `data/config.json` (autre fichier : `python -m lmu_assistant --config chemin.json`). API : `GET`/`PUT /api/config`.

## Enregistrer et rejouer une session

Pour développer et tester sans lancer le jeu, une session peut être enregistrée puis rejouée comme source de données.

```bash
# Enregistre chaque Snapshot diffusé (au rythme --hz) dans data/recordings/<date>_<source>.jsonl.gz
python -m lmu_assistant --source lmu --record
python -m lmu_assistant --source mock --record ma_session.jsonl.gz   # chemin explicite

# Rejoue un enregistrement (vitesse x2, en boucle)
python -m lmu_assistant --source replay --file samples/mock_60s.jsonl.gz --speed 2 --loop
```

Format : JSON Lines compressé en gzip. La 1re ligne est un en-tête (`format`, `version`, source, date), puis une ligne par image : `{"t": <secondes depuis le début>, "data": <Snapshot>}`. La relecture ignore les champs inconnus et met les valeurs par défaut pour les champs absents, donc les anciens enregistrements restent lisibles quand le modèle évolue. Sans `--loop`, la dernière image reste affichée en fin de fichier. Un fichier coupé par un arrêt brutal reste lisible jusqu'à la dernière image complète.

`samples/mock_60s.jsonl.gz` est un court exemple (60 s de la source simulée), utilisé aussi par les tests.

## Accès depuis une tablette / un téléphone

Le serveur écoute par défaut sur tout le réseau local. Au démarrage, il affiche les adresses à ouvrir depuis un autre appareil, par exemple :

```
LMU Assistant : http://localhost:8765  (source : mock)
  Réseau local : http://192.168.1.20:8765  (QR code : http://localhost:8765/connect.html)
```

- Sur le PC, le lien **Connexion** de la barre du haut (`/connect.html`) affiche ces adresses et un **QR code** à scanner avec la tablette ou le téléphone (connecté au même Wi-Fi).
- **Pare-feu Windows** : au premier lancement, Windows demande d'autoriser Python. Cocher **Réseaux privés** (pas « publics ») puis *Autoriser l'accès*. Si la fenêtre a été refusée : *Pare-feu Windows Defender > Autoriser une application* et cocher « Privé » pour Python. Le réseau Wi-Fi du PC doit aussi être en profil **privé**.
- Pour **désactiver** l'accès depuis le réseau (page visible uniquement sur le PC) : `python -m lmu_assistant --host 127.0.0.1`.

## Organisation

| Dossier | Rôle |
|---|---|
| `backend/lmu_assistant/` | Lecture des données du jeu, calculs, serveur HTTP + WebSocket |
| `backend/lmu_assistant/sources/` | Sources de données : `mock` (simulée), `lmu` (mémoire partagée du jeu), `replay` (relecture d'un enregistrement) |
| `samples/` | Petits enregistrements d'exemple pour les tests et démos |
| `web/` | Page web et widgets (HTML/CSS/JS sans build) |
| `overlay/` | Lanceur de l'overlay seul (le code est dans `lmu_assistant/overlay.py`) |
| `packaging/` | Construction de l'exécutable `LMU-Assistant.exe` (PyInstaller) |
| `docs/` | Notes techniques |

## Documents

- [PLAN.md](PLAN.md) : architecture et étapes.
- [FEATURES.md](FEATURES.md) : liste des fonctionnalités, ajoutées une par une.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

# LMU Assistant

Assistant « ingénieur augmenté » pour **Le Mans Ultimate** : les données simples utiles en course (carburant, énergie, delta, pneus…) façon outils type *Go Fast*, et des éléments hors course (stints, stratégie, analyse) qu'on ne voit pas dans le jeu.

Tout est affichable de deux façons, à partir des mêmes données :

- **Page web locale** : `http://localhost:8765`, sur le PC, une tablette ou un téléphone du réseau local.
- **Overlay en jeu** : une fenêtre transparente, sans bordure et toujours au premier plan qui affiche les mêmes widgets (jeu en mode *fenêtré sans bordure*).

> État : squelette. Le serveur tourne avec une source de données **simulée** (`mock`) pour développer sans le jeu. La lecture réelle des données LMU est la prochaine étape (voir [PLAN.md](PLAN.md)).

## Démarrage rapide

Prérequis : Python 3.11+ (Windows pour la lecture réelle du jeu, n'importe quel OS pour le mode simulé).

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS : source .venv/bin/activate)
pip install -e .

# Serveur + page web (données simulées)
python -m lmu_assistant --source mock
# puis ouvrir http://localhost:8765

# Overlay (dans un 2e terminal, serveur lancé)
pip install -r overlay/requirements.txt
python overlay/overlay.py
```

`--source lmu` sélectionnera la lecture réelle du jeu dès qu'elle sera implémentée.

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
| `overlay/` | Fenêtre overlay transparente qui affiche les widgets web |
| `docs/` | Notes techniques |

## Documents

- [PLAN.md](PLAN.md) : architecture et étapes.
- [FEATURES.md](FEATURES.md) : liste des fonctionnalités, ajoutées une par une.

## Tests

```bash
pip install -e ".[dev]"
pytest
```

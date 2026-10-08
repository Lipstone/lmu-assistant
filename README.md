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

## Réglages de l'overlay

- Page **Réglages overlay** (lien dans la barre du haut, ou `http://localhost:8765/settings.html`) : widgets affichés, position (pixels dans la fenêtre overlay), échelle, opacité, position/taille de la fenêtre, clics traversants et raccourci. « Enregistrer » applique tout de suite aux pages ouvertes ; l'overlay relit la fenêtre et le raccourci sous ~2 s.
- Sur la page normale, seule la visibilité des widgets s'applique (grille automatique).
- Raccourci global **afficher/masquer** : `ctrl+shift+o` par défaut (paquet `keyboard`, installé par `overlay/requirements.txt` sous Windows ; sans lui l'overlay marche, sans raccourci).
- **Clics traversants** (Windows, activé par défaut) : les clics passent au jeu, donc la fenêtre ne se déplace plus à la souris ; la placer depuis la page de réglages, ou lancer `python overlay/overlay.py --no-click-through` pour la déplacer à la main.
- Les réglages sont dans `data/config.json` (autre fichier : `python -m lmu_assistant --config chemin.json`). API : `GET`/`PUT /api/config`.

## Organisation

| Dossier | Rôle |
|---|---|
| `backend/lmu_assistant/` | Lecture des données du jeu, calculs, serveur HTTP + WebSocket |
| `backend/lmu_assistant/sources/` | Sources de données : `mock` (simulée), `lmu` (mémoire partagée du jeu) |
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

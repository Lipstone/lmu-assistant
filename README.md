# LMU Assistant

Assistant « ingénieur augmenté » pour **Le Mans Ultimate** : les données simples utiles en course (carburant, énergie, delta, pneus…) façon outils type *Go Fast*, et des éléments hors course (stints, stratégie, analyse) qu'on ne voit pas dans le jeu.

Tout est affichable de deux façons, à partir des mêmes données :

- **Page web locale** : `http://localhost:8765`, sur le PC, une tablette ou un téléphone du réseau local.
- **Overlay en jeu** : une petite fenêtre transparente, sans bordure et toujours au premier plan **par widget**, placée où l'on veut sur l'écran, qui affiche les mêmes widgets (jeu en mode *fenêtré sans bordure*).

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

## Carburant et énergie virtuelle (F01, F02)

Le widget **Carburant** affiche le niveau, la conso du dernier tour et la moyenne des 5 derniers tours valides (nombre de tours entre parenthèses), les tours possibles avec le carburant à bord, les tours restant jusqu'à l'arrivée et le **carburant à ajouter pour finir** (« assez » s'il n'en manque pas). Les calculs sont faits côté serveur (`backend/lmu_assistant/fuel.py`), donc identiques sur la page web, la tablette et l'overlay.

- Un tour compte dans la moyenne s'il a été suivi depuis la ligne, sans passage aux stands ni ravitaillement. La moyenne repart de zéro quand la session, la piste ou la voiture change.
- Course chronométrée : à la fin du temps on finit le tour en cours, l'estimation arrondit donc au passage de ligne suivant (avec le temps au tour moyen). Course au nombre de tours : tours restants d'après `mMaxLaps`.
- Pas de marge de sécurité ajoutée : le chiffre « À ajouter » est le strict nécessaire.
- **Énergie virtuelle (% EV)** : sur les voitures qui en ont (Hypercar, LMGT3), le widget passe en **Énergie virtuelle** avec les mêmes calculs en % (dernier tour, moyenne, tours restants, % à ajouter), et rappelle les litres sur une ligne. Réglage « Widget Carburant » dans Réglages overlay : Auto (par défaut), Litres ou % énergie virtuelle.

## Delta (F03)

Le widget **Delta** affiche en gros l'écart en direct avec le tour de référence, au même endroit de la piste (vert et négatif = plus rapide, rouge et positif = plus lent), une barre centrée (pleine à ±2 s), le **temps prévu** du tour en cours, le temps de la référence, et l'écart avec chacune des trois références :

- **meilleur** tour de la session (référence par défaut) ;
- **dernier** tour ;
- **record** personnel pour la piste et la voiture, enregistré dans `data/records.json` et gardé d'une session à l'autre (seulement en lecture réelle du jeu : les données simulées ou rejouées ne changent pas les records).

La référence affichée en gros se choisit dans Réglages overlay (« Widget Delta »). Calculs côté serveur (`backend/lmu_assistant/delta.py`) : pendant chaque tour on relève le temps écoulé selon l'avancement dans le tour ; un tour sert de référence s'il a été suivi depuis la ligne, sans passage aux stands ni trou dans les relevés. Meilleur et dernier tour repartent de zéro quand la session, la piste ou la voiture change. Le delta est masqué quand il n'a pas de sens (écart de plus de 25 % du tour, par exemple aux stands).

## Temps au tour (F04)

Le widget **Temps au tour** affiche le tour en cours (rouge s'il est invalidé par le jeu), le dernier tour (vert s'il est le meilleur), le meilleur tour, la **moyenne des N derniers tours valides** (N entre parenthèses, 5 par défaut, réglable de 2 à 20 dans Réglages overlay) et la **régularité** : écart-type de ces mêmes tours (vert sous ±0,3 s, orange au-delà de ±1 s). En dessous, les 5 derniers tours avec l'écart au meilleur tour valide de la session ; les tours exclus de la moyenne sont barrés avec la raison : **stand** (tour de sortie ou de rentrée), **invalide** (limites de piste) ou **partiel** (appli lancée en cours de tour).

Calculs côté serveur (`backend/lmu_assistant/laptimes.py`), avec le temps du tour publié par le jeu ; tout repart de zéro quand la session, la piste ou la voiture change.

## Pneus (F05)

Le widget **Pneus** montre les quatre roues comme vues du dessus (AVG, AVD en haut, ARG, ARD en bas). Pour chaque roue : les trois températures **extérieur / milieu / intérieur**, l'extérieur dessiné du côté extérieur de la voiture (à gauche pour les roues gauches, à droite pour les roues droites), la **pression** et l'**usure** (% de gomme restante, orange sous 30 %).

Couleur des températures selon la **plage idéale** (75 à 100 °C par défaut) : bleu en dessous, vert dedans, orange au-dessus, rouge à plus de 15 °C au-dessus. Plage et unité de pression (kPa, psi ou bar) se règlent dans Réglages overlay (« Widget Pneus »). L'usure est le `mWear` du jeu recopié tel quel, supposé 1 = neuf : à vérifier en jeu.

## Freins (F06)

Le widget **Freins** affiche la température de chaque frein (AVG, AVD, ARG, ARD) et son **pic** sur le tour précédent (sur le tour en cours pendant le premier tour). Couleur : bleu sous 200 °C (freins froids), vert, orange à moins de 100 °C du seuil, rouge au-delà. **Alerte surchauffe** : un bandeau rouge clignotant nomme les roues au-dessus du seuil (800 °C par défaut, réglable dans Réglages overlay, « Widget Freins ») ; il reste affiché jusqu'à ce que la température redescende de 30 °C sous le seuil, pour ne pas clignoter dans chaque freinage. Le bon seuil dépend des freins : plus haut pour les disques carbone (Hypercar, LMP2) que pour l'acier (GT3).

Calculs côté serveur (`backend/lmu_assistant/brakes.py`), avec `mBrakeTemp` du jeu (déjà en °C).

## Relative (F07)

Le widget **Relative** montre les 3 voitures juste **devant** et les 3 juste **derrière** sur la piste (toutes classes), le joueur au milieu en surbrillance. Par ligne : position **dans sa classe** sur la couleur de la classe (rouge Hypercar, bleu LMP2, vert LMGT3 ; position au général au survol), numéro, pilote, tours d'avance ou de retard au classement et **écart en secondes** sur la piste. **Orange** (+1T) : la voiture a un tour d'avance sur nous et va nous doubler ; **bleu** (−1T) : elle a un tour de retard, c'est nous qui la doublons. Les voitures d'une autre classe sont légèrement grisées, celles aux stands marquées STAND.

Calculs côté serveur (`backend/lmu_assistant/relative.py`) à partir du classement du jeu : écart sur la piste (avancement dans le tour, ramené à moins d'un demi-tour devant ou derrière) × notre meilleur tour (sinon dernier tour, sinon estimation du jeu).

## Classement (F08)

Le widget **Classement** donne un classement simplifié **par classe**, la classe du joueur en premier, puis les autres dans l'ordre de leur meilleure voiture au général (nombre de voitures entre parenthèses). Dans chaque classe : les 3 premiers, et dans la classe du joueur la voiture juste devant, le joueur (en surbrillance) et celle juste derrière ; « ⋯ » marque les voitures omises. Par ligne : position dans la classe, numéro, pilote, **écart au leader de la classe** (en secondes, ou en tours dès qu'il y a au moins un tour, « +1T »), et **dernier tour**. L'écart à la voiture juste devant s'affiche au survol ; les voitures aux stands sont marquées STAND.

Calculs côté serveur (`backend/lmu_assistant/standings.py`) à partir du classement du jeu (`mPlace`, `mVehicleClass`, `mTimeBehindLeader`, distance parcourue).

## Fenêtre de stand (F09)

Le widget **Fenêtre de stand** dit quand s'arrêter et ce que ça coûte :

- **tours avant l'arrêt obligatoire** (en gros, orange sous 2 tours) : le plus petit des tours restants en carburant et en énergie virtuelle, avec ce qui limite ;
- **rentrer au plus tard** : le dernier tour à la fin duquel on peut encore rentrer avec ce qu'il reste ;
- **fenêtre** : du premier tour où s'arrêter permet de finir avec le nombre d'arrêts minimum (pleins complets : réservoir ou 100 % d'énergie) jusqu'au dernier tour possible ; « ouverte » en vert quand on y est, « aucun arrêt » s'il y a assez pour finir ;
- **arrêts restants** jusqu'à l'arrivée, avec le nombre de tours d'un plein ;
- **temps perdu au stand** : mesuré sur nos arrêts de la session (temps des tours de rentrée et de sortie moins autant de tours de notre moyenne F04, moyenne des 3 derniers arrêts), sinon la valeur par défaut des Réglages overlay (60 s, « Widget Stand ») ;
- **sortie estimée** : notre position dans la classe si l'on s'arrêtait maintenant (les voitures de la classe derrière nous à moins de ce temps nous repassent).

Calculs côté serveur (`backend/lmu_assistant/pitstop.py`) à partir des moyennes de consommation (F01, F02), des temps au tour (F04) et du classement (F07). Les estimations ne valent qu'après un tour complet suivi (moyennes de consommation) et ne comptent pas de marge de sécurité.

## Session et piste (F10)

Le widget **Session et piste** affiche le **temps restant** (en tours pour une course au nombre de tours) avec une barre d'avancement de la session, le **drapeau** du moment et la météo :

- **drapeau**, du plus important au moins important : rouge (session arrêtée), damier (arrivée), **FCY / voiture de sécurité** (clignotant, avec l'état des stands : fermés, ouverts, dernier tour…), **jaune local** dans notre secteur ou le suivant (« Jaune S2 »), bleu, vert ; un jaune plus loin sur la piste est seulement mentionné (« Vert · jaune S3 ») ;
- températures **air / piste** et **évolution de la piste sur 10 minutes** (piste qui chauffe ou refroidit) ;
- **pluie** et **piste mouillée** en % (orange dès qu'il pleut ou que la piste est mouillée à 10 %), **ciel**, niveau de **grip** (gomme sur la piste : vert, faible, moyen, élevé, saturé) et heure dans le jeu.

Calculs côté serveur (`backend/lmu_assistant/session.py`) à partir de la phase de jeu, des drapeaux et de la météo de la mémoire partagée (`mGamePhase`, `mYellowFlagState`, `mSectorFlag`, `mFlag`, `mAmbientTemp`, `mTrackTemp`, `mRaining`, `mAvgPathWetness`, `mTrackGripLevel`, `mCloudCoverage`, `mTimeOfDay`).

## Dégâts (F11)

Le widget **Dégâts** montre la voiture vue de dessus en 8 zones (avant gauche, avant, avant droit, côtés, arrière gauche, arrière, arrière droit) : gris = intacte, orange = déformation légère, rouge = lourde, avec l'**état de la carrosserie** en % au centre. En dessous :

- **aéro** et **suspension** (la roue la plus touchée, le détail des 4 au survol), orange sous 90 %, et **temps de réparation** estimé au stand : ces trois valeurs viennent de l'**API REST locale du jeu** (`http://127.0.0.1:6397`, interrogée toutes les 2 s dans un fil séparé) et restent à « – » si elle ne répond pas ;
- **dernier choc** (il y a combien de temps ; force et nombre de chocs de la session au survol) ;
- températures **eau / huile** du moteur ;
- bandeau rouge si une roue est **crevée** ou **arrachée**, si des pièces sont arrachées ou si le moteur **surchauffe**.

Calculs côté serveur (`backend/lmu_assistant/damage.py`) à partir de `mDentSeverity`, `mFlat`, `mDetached`, `mLastImpactET`, `mLastImpactMagnitude`, `mOverheating`, `mEngineWaterTemp` et `mEngineOilTemp` de la mémoire partagée.

## Inputs (F12)

Le widget **Inputs** montre les commandes du pilote en direct : une **trace courte** de l'accélérateur (vert) et du frein (rouge) sur les dernières secondes (8 s par défaut, de 2 à 30 s dans Réglages overlay, « Widget Inputs »), les jauges **accélérateur / frein / embrayage** en %, la position du **volant** (barre centrée et angle en degrés quand le jeu donne la rotation du volant, sinon en %) et les témoins **ABS** et **TC** qui s'allument quand l'aide intervient.

Valeurs brutes du pilote (`mUnfilteredThrottle`, `mUnfilteredBrake`, `mUnfilteredClutch`, `mUnfilteredSteering`, `mPhysicalSteeringWheelRange`, `mABSActive`, `mTCActive`) ; la trace est gardée par la page à partir des images reçues (10 par seconde par défaut, `--hz` pour plus de finesse).

## Analyse hors course

La page **Analyse** (lien dans la barre du haut, `http://localhost:8765/analyse.html`) rassemble ce qui sert après la course ou entre deux relais, à partir de l'historique enregistré pendant que l'on roule.

### Historique des tours (F20)

Chaque tour terminé est enregistré dans une base **SQLite** (`data/history.sqlite`, à côté de l'exe) : temps et **secteurs**, tour valide / invalidé / stand, **arrêt** (voiture immobile aux stands), ravitaillement et pneus changés, **carburant et énergie** consommés (sans ravitaillement pendant le tour), usure, températures et pressions des pneus en fin de tour, conditions (air, piste, pluie, piste mouillée, grip), position, pilote, chocs, et une trace du tour (temps et vitesse tous les 200es de tour, pour la comparaison de tours). Les tours d'une même session de jeu, piste et voiture forment une **session**.

Sur la page Analyse : choix de la session (la plus récente d'abord ; la page suit la session en cours et ajoute les nouveaux tours d'elle-même), tableau des tours avec le meilleur tour en vert et les **meilleurs secteurs en violet**, et bouton pour supprimer une session.

Par défaut seule la lecture du jeu est enregistrée : les données simulées et les relectures ne remplissent pas l'historique. `--history on` enregistre toutes les sources (pour essayer avec `--source mock`), `--history off` n'enregistre rien, `--history-file chemin.sqlite` change de base. API : `GET /api/history/sessions`, `GET`/`DELETE /api/history/sessions/{id}`, `GET /api/history/laps/{id}` (avec la trace). Code : `backend/lmu_assistant/history.py`.

### Relais et dégradation des pneus (F21, F22)

Les tours sont découpés automatiquement en **relais** : un nouveau relais commence au tour de sortie d'un arrêt au stand (voiture immobile aux stands ou ravitaillée) ou quand le pilote change. Section **Relais** de la page Analyse, une ligne par relais : tours, pilote, durée, moyenne, meilleur tour, régularité (tours propres : valides et hors stand), consommation de carburant et d'énergie par tour, pneus (neufs, ou leur âge en tours au début du relais), dégradation, usure par tour du pneu qui s'use le plus et gomme restante en fin de relais.

Section **Dégradation des pneus** : pour le relais choisi (ou tous les relais superposés), les temps au tour propres selon le tour dans le relais avec leur **tendance** (droite de régression : la pente est le temps perdu par tour), et la **gomme restante de chaque pneu** tour après tour. Le résumé donne la dégradation, les 3 premiers et 3 derniers tours, l'usure par tour de chaque pneu et le nombre de tours avant qu'un pneu ne descende à 30 %.

Widget **Relais** (page web et overlay, pour suivre le relais en cours pendant la course) : numéro du relais, tours faits, durée, moyenne et régularité, dégradation (orange au-delà de +0,15 s par tour), consommation par tour, âge des pneus et gomme restante du pneu le plus usé avec son usure par tour (orange à moins de 3 tours des 30 %). Il marche même sans enregistrement dans l'historique (données simulées).

Calculs côté serveur (`backend/lmu_assistant/analysis.py`).

### Comparaison de tours (F23)

Section **Comparaison de tours** de la page Analyse : on choisit deux tours de la session (par défaut A = meilleur tour valide, B = dernier tour valide) et on voit :

- l'écart **par secteur** et sur le tour (B − A : rouge quand B est plus lent, vert quand il est plus rapide) ;
- le **meilleur tour théorique** : somme des meilleurs secteurs des tours valides (avec le tour de chacun) et ce qu'il reste à gagner par rapport au meilleur tour ;
- l'**écart cumulé** de B sur A tout le long du tour (d'après les traces enregistrées, là où le temps se perd) et les deux courbes de **vitesse**.

API : `GET /api/history/compare?a=<id du tour A>&b=<id du tour B>` ; calculs dans `backend/lmu_assistant/analysis.py`.

## Réglages de l'overlay

- Page **Réglages overlay** (lien dans la barre du haut, ou `http://localhost:8765/settings.html`) : widgets affichés, position de chaque fenêtre sur l'écran (pixels, coin haut gauche ; valeurs négatives pour un écran à gauche de l'écran principal), échelle (taille de la fenêtre), opacité et **transparence du fond** (globales ou par widget), clics traversants et raccourci. Un aperçu montre la place des fenêtres sur l'écran. « Enregistrer » applique tout de suite aux pages ouvertes ; l'overlay déplace, redimensionne, ouvre ou masque ses fenêtres sous ~2 s.
- **Transparence** : « Opacité » rend tout le widget transparent (texte compris) ; « Fond » ne touche que le fond (0 = chiffres posés directement sur l'image du jeu). Les colonnes Opacité/Fond d'un widget remplacent les valeurs globales ; laisser vide pour garder la valeur globale.
- Sur la page normale, seule la visibilité des widgets s'applique (grille automatique).
- Raccourci global **afficher/masquer** : `ctrl+shift+o` par défaut (paquet `keyboard`, inclus dans l'exe et dans `pip install -e ".[overlay]"` sous Windows ; sans lui l'overlay marche, sans raccourci).
- **Placement à la souris** : activer le **mode placement** (raccourci `ctrl+shift+p`, ou case « Mode placement » dans les réglages). Chaque fenêtre est alors encadrée : la faire glisser pour la déplacer, tirer la poignée en bas à droite pour l'agrandir ou la réduire. Positions et tailles sont enregistrées automatiquement ; refaire le raccourci pour revenir en jeu.
- **Clics traversants** (Windows, activé par défaut) : hors mode placement, les clics passent au jeu à travers les fenêtres.
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

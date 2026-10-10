# Fonctionnalités

Liste de travail : chaque ligne est ajoutée à la demande. Toutes sont prévues pour la **page web** et l'**overlay**, sauf mention contraire.

Légende état : ⬜ à faire · 🟨 en cours · ✅ fait

## En course (données simples, type Go Fast)

| ID | Fonctionnalité | Détail | État |
|---|---|---|---|
| F01 | Carburant | Niveau, conso dernier tour et moyenne, tours restants, carburant à ajouter pour finir ; transparence réglable (widget et fond) | ✅ |
| F02 | Énergie virtuelle | Énergie restante, conso par tour, tours restants, % à ajouter pour finir ; widget Carburant en % EV automatiquement (ou forcé L / %) | ✅ |
| F03 | Delta | Écart en direct au meilleur tour de la session, au dernier tour ou au record personnel (piste + voiture, gardé d'une session à l'autre), temps prévu | ✅ |
| F04 | Temps au tour | Dernier, meilleur, moyenne des N derniers, régularité | ✅ |
| F05 | Pneus | Températures (int/milieu/ext), pressions, usure par roue | ✅ |
| F06 | Freins | Températures par roue, alerte surchauffe | ✅ |
| F07 | Relative | Pilotes devant/derrière avec écart, classe, tours d'avance/retard ; colonnes optionnelles dégâts globaux (0 % = intacte), carburant / énergie restant, conso par tour, pénalités, gomme, relais sur le train de pneus, meilleur et dernier tour de chaque voiture | ✅ |
| F08 | Classement | Classement simplifié par classe, intervalle avec le pilote devant (écart au leader au survol) ; colonnes optionnelles dégâts globaux (0 % = intacte), carburant / énergie restant, conso par tour, pénalités, gomme avant/arrière en ronds de couleur (affichée par défaut), relais sur le train de pneus, meilleur tour et dernier tour (affiché par défaut) de chaque voiture | ✅ |
| F09 | Fenêtre de stand | Tours avant arrêt obligatoire (carburant/énergie), temps perdu au stand estimé | ✅ |
| F10 | Session et piste | Temps restant, drapeaux (jaune local, FCY, bleu…), météo, température piste/air et son évolution, grip | ✅ |
| F11 | Dégâts | Voiture vue de dessus (SVG) : dégâts carrosserie (8 zones, 0 % = intacte), roues (crevaison, arrachée) et suspensions dessinées à part, aéro (lame, aileron) ; aéro, suspension, réparation estimée, roues, chocs, moteur | ✅ |
| F12 | Inputs | Pédales et volant en direct (trace courte réglable), témoins ABS / TC | ✅ |
| F13 | Météo et prévision | Prévision du jeu (5 points : ciel, air, risque de pluie) placée dans le temps, résumé « pluie dans X min », tendances estimées (pluie, piste mouillée, température piste) et temps avant piste sèche / mouillée | ✅ |
| F14 | Shift light | 10 LED jusqu'au régime de passage, bleu pour passer ; GT3 : régimes optimaux du tableau « LMU GT3 optimal shift point », autres voitures : % du régime max | ✅ |

## Hors course (ingénieur augmenté)

| ID | Fonctionnalité | Détail | État |
|---|---|---|---|
| F20 | Historique des tours | Enregistrement de chaque tour (temps, secteurs, carburant, pneus, météo, trace) en SQLite, page Analyse | ✅ |
| F21 | Relais (stints) | Découpage automatique en relais, résumé par relais, widget du relais en cours | ✅ |
| F22 | Dégradation pneus | Évolution des temps (tendance en s/tour) et de l'usure par pneu sur un relais | ✅ |
| F23 | Comparaison de tours | Secteurs, meilleur tour théorique, écart par secteur, écart cumulé et vitesse le long du tour | ✅ |
| F24 | Planificateur de stratégie | Durée de course, nombre d'arrêts, carburant et énergie par relais, pneus, scénarios comparés | ✅ |
| F25 | Rapport de session | Résumé post-session : rythme, régularité, incidents, conso | ✅ |
| F26 | Notes de setup | Notes liées à une voiture/piste/session | ✅ |
| F27 | Export | CSV/JSON des tours et relais (Excel français ou international), JSON complet avec traces et notes | ✅ |
| F28 | Évolution conditions | Courbes température piste, météo, grip au fil de la session | ✅ |

Les fonctionnalités hors course sont surtout pour la page web ; une version compacte en overlay sera proposée quand c'est utile (par exemple l'état du relais en cours).

## Socle technique

| ID | Élément | Détail | État |
|---|---|---|---|
| T01 | Serveur local | FastAPI, HTTP + WebSocket `/ws` | ✅ squelette |
| T02 | Source simulée | Données factices pour développer sans le jeu | ✅ squelette |
| T03 | Page web | Page de base connectée au WebSocket | ✅ squelette |
| T04 | Overlay | Une fenêtre transparente toujours au premier plan par widget | ✅ |
| T05 | Lecture LMU | Mémoire partagée du jeu → `Snapshot` | ✅ |
| T06 | Config overlay | Choix, position écran et taille de chaque fenêtre widget (réglages ou à la souris en mode placement), opacité du fond et du texte par widget, raccourcis afficher/masquer et placement | ✅ |
| T07 | Enregistrement / relecture | Enregistrer une session brute et la rejouer comme source | ✅ |
| T08 | Accès réseau local | Page accessible depuis tablette/téléphone, QR code | ✅ |
| T09 | Exécutable Windows (obligatoire) | L'application se lance via `LMU-Assistant.exe` (serveur + overlay), construit par la CI | ✅ |

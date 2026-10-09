# Données LMU : mémoire partagée

Source `lmu` : `backend/lmu_assistant/sources/lmu_shared_memory.py`.

## Interface utilisée

Le Mans Ultimate (moteur rFactor 2) fournit une **interface de mémoire partagée native** : le jeu écrit en continu une zone Windows nommée **`LMU_Data`**. Son format est décrit par les en-têtes `SharedMemoryInterface.hpp` et `InternalsPlugin.hpp` livrés avec le jeu dans `Support\SharedMemoryInterface` (dossier d'installation Steam). Ces en-têtes ne sont pas redistribuables, ils ne sont donc pas copiés dans le dépôt.

- **Aucun plugin à installer ni à activer** : la zone existe dès que le jeu est lancé.
- Le plugin rFactor 2 *rF2SharedMemoryMapPlugin* (zones `$rFactor2SMMP_Telemetry$`, `$rFactor2SMMP_Scoring$`…) n'est **pas** utilisé : l'interface native le remplace et évite d'installer une DLL tierce dans le jeu.

| Élément | Valeur |
|---|---|
| Nom de la zone | `LMU_Data` |
| Taille | 324 820 octets (`sizeof(SharedMemoryObjectOut)`) |
| Alignement | `#pragma pack(4)` → `_pack_ = 4` en ctypes |
| Véhicules max | 104 |
| Verrou du jeu (non utilisé) | zone `LMU_SharedMemoryLockData` (8 octets) + événement `LMU_SharedMemoryLockEvent` |

### Organisation de `LMU_Data` (`SharedMemoryObjectOut`)

| Bloc | Décalage | Contenu |
|---|---|---|
| `generic` | 0 | compteurs d'événements `SME_*` (16 × uint32), `gameVersion`, `FFBTorque`, `appInfo` (dont `mAppWindow`, HWND du jeu, à l'octet 72) |
| `paths` | 332 | 5 chemins de 260 caractères |
| `scoring` | 1 632 | `ScoringInfoV01` (session, piste), puis 104 × `VehicleScoringInfoV01` (584 octets, à partir de 2 192), puis le flux de résultats |
| `telemetry` | 128 464 | `activeVehicles`, `playerVehicleIdx`, `playerHasVehicle` (uint8 ×3), puis 104 × `TelemInfoV01` (1 888 octets, à partir de 128 468) |

Ces décalages sont vérifiés par un test (`tests/test_lmu_shared_memory.py::test_layout_matches_known_offsets`) contre une seconde source indépendante.

## Lecture

1. **Ouverture** (Windows) : `OpenFileMappingW` vérifie que le jeu a créé la zone (sans la créer nous-mêmes), puis `mmap.mmap(-1, 324820, tagname="LMU_Data", access=ACCESS_READ)`.
2. **Jeu absent** : `Snapshot(connected=False, source="lmu")`, nouvel essai d'ouverture toutes les 2 s. Hors Windows, la source reste toujours déconnectée.
3. **Jeu fermé** : si la fenêtre `appInfo.mAppWindow` n'existe plus (`IsWindow`), la zone est relâchée (sinon notre handle la garderait en vie avec des données figées).
4. **Cohérence** : l'interface native n'a pas de compteurs de version début/fin comme le plugin rF2. On lit une « signature » (compteurs `SME_*`, `mCurrentET` du scoring, en-tête télémétrie, `mElapsedTime` de la voiture du joueur) avant et après la copie complète ; si elle a changé, le jeu écrivait pendant la copie et on recommence (5 essais max, puis on garde la dernière copie).
5. **Conversion** : `parse_buffer(octets) → Snapshot`, indépendante de Windows (testée sur des tampons synthétiques).

Le verrou officiel du jeu (`LMU_SharedMemoryLockData`) n'est pas pris : il demande des opérations atomiques sur la mémoire partagée, peu sûres en Python pur. À reconsidérer si des lectures incohérentes apparaissent en jeu.

## Voiture du joueur

1. Scoring : premier véhicule (parmi `mNumVehicles`) avec `mIsPlayer`, sinon `mControl == 0` (joueur local).
2. Télémétrie : entrée de même `mID` parmi `activeVehicles` (les index scoring et télémétrie ne correspondent pas forcément), sinon `telemInfo[playerVehicleIdx]` si `playerHasVehicle`.

## Champs utilisés

| Snapshot | Champ LMU | Unité / conversion |
|---|---|---|
| `track` | `ScoringInfoV01.mTrackName` (sinon `TelemInfoV01.mTrackName`) | texte |
| `session` | `ScoringInfoV01.mSession` | 0 = journée test, 1-4 = essais, 5-8 = qualification, 9 = warm-up, 10-13 = course |
| `session_time_left_s` | `mEndET - mCurrentET` (si `mEndET > 0`) | s |
| `car` | `VehicleScoringInfoV01.mVehicleName` (sinon `TelemInfoV01.mVehicleName`) | texte |
| `position` | `mPlace` | à partir de 1 |
| `lap` | `mTotalLaps + 1` (tour en cours ; sans scoring : `TelemInfoV01.mLapNumber`) | |
| `last_lap_s`, `best_lap_s` | `mLastLapTime`, `mBestLapTime` | s ; `None` si ≤ 0 |
| `current_lap_s` | `TelemInfoV01.mElapsedTime - mLapStartET` | s |
| `speed_kmh` | norme de `mLocalVel` | m/s × 3,6 |
| `rpm` | `mEngineRPM` | tr/min |
| `gear` | `mGear` | -1 = R, 0 = N |
| `fuel_l`, `fuel_capacity_l` | `mFuel`, `mFuelCapacity` | litres |
| `virtual_energy_pct` | `TelemInfoV01.mVirtualEnergy` | fraction 0-1 × 100 ; `None` si 0 (voiture sans énergie virtuelle) |
| `max_laps` | `ScoringInfoV01.mMaxLaps` | `None` si ≤ 0 ou ≥ 10 000 (course chronométrée) |
| `lap_fraction` | `VehicleScoringInfoV01.mLapDist / ScoringInfoV01.mLapDist` | 0-1, borné |
| `in_pits` | `mInPits` | |
| `lap_invalid` | `TelemInfoV01.mLapInvalidated` | tour en cours invalidé (limites de piste), exclu de la moyenne des temps (F04) |
| `wheels[i]` | `mWheels[i]`, ordre 0 = AVG, 1 = AVD, 2 = ARG, 3 = ARD (même ordre que Snapshot) | |
| `temp_c` | `mTemperature[3]` | Kelvin − 273,15 → °C |
| `pressure_kpa` | `mPressure` | kPa |
| `wear` | `mWear` | fraction 0-1 recopiée telle quelle ; supposée 1,0 = neuf (à vérifier) |
| `brake_temp_c` | `mBrakeTemp` | déjà en °C |

**Intérieur / extérieur** : `mTemperature` est en gauche / centre / droite vu du pilote, pas intérieur / extérieur. Pour les roues gauches (AVG, ARG), l'extérieur est à gauche : `(int, milieu, ext) = (T[2], T[1], T[0])`. Pour les roues droites (AVD, ARD) : `(T[0], T[1], T[2])`.

Delta (F03) : calculé par l'appli à partir de `mLapDist` (scoring, avancé à l'instant de la télémétrie avec la vitesse) et du temps du tour, pour avoir aussi le dernier tour et le record personnel comme référence. Le `mDeltaBest` du jeu n'est pas utilisé.

**Toutes les voitures** (`vehicles`, F07 et suivantes) : une entrée par `VehicleScoringInfoV01` parmi `mNumVehicles`, triée par `mPlace`. `driver` = `mDriverName`, `car_class` = `mVehicleClass`, `laps` = `mTotalLaps`, `lap_fraction` = `mLapDist / ScoringInfoV01.mLapDist`, `last_lap_s` / `best_lap_s` / `estimated_lap_s` = `mLastLapTime` / `mBestLapTime` / `mEstimatedLapTime`, `time_behind_leader_s` / `laps_behind_leader` = `mTimeBehindLeader` / `mLapsBehindLeader`, `in_pits` = `mInPits`, `pitstops` = `mNumPitstops`, `is_player` = même `mID` que le joueur. `number` = le nombre après `#` dans `mVehicleName` (vide s'il n'y en a pas).

**Dégâts et carburant des autres voitures** (colonnes optionnelles du relative et du classement) : le jeu écrit un `TelemInfoV01` par voiture active (`activeVehicles`), associé à la voiture de scoring par `mID`. Pour chaque voiture : `dents` = `mDentSeverity` (même ordre que le joueur), `parts_detached` = `mDetached`, `wheels_off` = nombre de roues `mFlat` ou `mDetached`, `fuel_l` = `mFuel` (laissé à `None` si 0 sans `mFuelCapacity`, donnée non transmise), `energy_pct` = `mVirtualEnergy` × 100. Sans télémétrie pour une voiture, ces champs restent `None` (« – » à l'écran). **La consommation des autres voitures n'est pas donnée par le jeu** : `opponents.py` l'estime à partir du niveau relevé à chaque passage de ligne (moyenne des 3 derniers tours sans arrêt ni plein). L'aéro et la suspension des autres voitures ne sont pas disponibles (API REST : voiture du joueur seulement).

**Session et piste** (F10) : `session_elapsed_s` / `session_length_s` = `mCurrentET` / `mEndET` ; `game_phase` = `mGamePhase` (0 avant la session, 1 à 4 procédure de départ, 5 vert, 6 FCY / voiture de sécurité, 7 arrêtée, 8 terminée, 9 pause) ; `yellow_flag_state` = `mYellowFlagState` (FCY seulement : 1 en attente, 2 stands fermés, 3 leaders aux stands, 4 stands ouverts, 5 dernier tour, 6 reprise ; `char` signé) ; `sector_flags` = `mSectorFlag` remis dans l'ordre S1, S2, S3 (même convention que `mSector` : index 0 = secteur 3), 1 = jaune local ; `player_flag` = `mFlag` du joueur (0 vert, 6 bleu) ; `sector` = `mSector` du joueur (0 = S3, 1 = S1, 2 = S2) ; `air_temp_c`, `track_temp_c` = `mAmbientTemp`, `mTrackTemp` (°C) ; `raining` = `mRaining` (0-1) ; `wetness` = `mAvgPathWetness` (0-1) ; `track_grip` = `mTrackGripLevel` (0 vert, 1 faible, 2 moyen, 3 élevé, 4 saturé) ; `cloud_coverage` = `mCloudCoverage` (0 dégagé … 7 couvert et pluie fine) ; `time_of_day_s` = `mTimeOfDay` (0 à 86 400).

**Dégâts** (F11) : `dents` = `mDentSeverity` (0 rien, 1 léger, 2 lourd) remis dans l'ordre AVG, AV, AVD, G, D, ARG, AR, ARD (ordre rF2 : 0 avant, 1 avant gauche, 2 gauche, 3 arrière gauche, 4 arrière, 5 arrière droit, 6 droite, 7 avant droit, comme TinyPedal) ; `parts_detached` = `TelemInfoV01.mDetached` ; `wheels[i].flat` / `detached` = `mFlat` / `mDetached` de la roue ; `last_impact_et` / `last_impact_magnitude` = `mLastImpactET` / `mLastImpactMagnitude` ; `engine_overheating` = `mOverheating` ; `water_temp_c` / `oil_temp_c` = `mEngineWaterTemp` / `mEngineOilTemp` (°C).

**Secteurs** (F20) : `last_sector1_s` / `last_sector2_s` = `mLastSector1` / `mLastSector2` du joueur (temps cumulé depuis la ligne à la fin des secteurs 1 et 2 du dernier tour ; S2 = `mLastSector2 − mLastSector1`, S3 = temps du tour − `mLastSector2`).

**Inputs** (F12) : `throttle`, `brake`, `clutch` = `mUnfilteredThrottle`, `mUnfilteredBrake`, `mUnfilteredClutch` (0-1) ; `steering` = `mUnfilteredSteering` (-1 gauche … 1 droite) ; `steering_range_deg` = `mPhysicalSteeringWheelRange` (rotation butée à butée, `None` hors 90-2000°) ; `abs_active`, `tc_active` = `mABSActive`, `mTCActive`.

**API REST locale du jeu** (`http://127.0.0.1:6397`, interrogée toutes les 2 s dans un fil séparé, comme TinyPedal) : `aero_damage` = `wearables.body.aero` et `suspension_damage` = `wearables.suspension` (4 valeurs, 0 intacte … 1 détruite) de `GET /rest/garage/UIScreen/RepairAndRefuel` ; `repair_time_s` = `damage` de `GET /rest/strategy/pitstop-estimate` (s). Si l'API ne répond pas, ces champs restent `None`.

**Prévision météo** (F13) : `GET /rest/sessions/weather` (toutes les 15 s) donne pour `PRACTICE`, `QUALIFY` et `RACE` cinq points `START`, `NODE_25`, `NODE_50`, `NODE_75`, `FINISH`, chacun avec `WNV_SKY.currentValue` (ciel 0-10 : 0 dégagé, 1 quelques nuages, 2 partiellement nuageux, 3 très nuageux, 4 couvert, 5 bruine, 6 pluie fine, 7 couvert et pluie fine, 8 pluie, 9 forte pluie, 10 orage), `WNV_TEMPERATURE.currentValue` (air, °C) et `WNV_RAIN_CHANCE.currentValue` (risque de pluie, %), lu comme TinyPedal (`process/weather.py`). `weather_forecast` = les points de la session en cours (`mSession` : essais et journée test → `PRACTICE`, qualification → `QUALIFY`, warm-up et course → `RACE`), placés aux fractions 0 / 0,25 / 0,5 / 0,75 / 1 de la session d'après leur nom (TinyPedal les place, lui, à 0 / 0,2 / 0,4 / 0,6 / 0,8 : à vérifier en jeu).

Champs disponibles pour plus tard (déjà décrits dans les structures) : `mDeltaBest`, écarts `mTimeGapCarAhead/Behind`, réglages TC/ABS, composés de pneus, secteurs, état des stands.

## Sources

- **Structures complètes** (types, ordre des champs, `pack=4`, nom `LMU_Data`, unités en commentaire) : TinyPedal, *pyLMUSharedMemory*, `lmu_data.py`, transcription Python de `SharedMemoryInterface.hpp` / `InternalsPlugin.hpp` fournis par S397 : <https://github.com/TinyPedal/pyLMUSharedMemory/blob/master/lmu_data.py>
- **Vérification indépendante des décalages et du verrou** (taille 324 820, scoring à 1 632, véhicules 584 octets à 2 192, télémétrie à 128 464, 1 888 octets par véhicule, `LMU_SharedMemoryLockData` / `LMU_SharedMemoryLockEvent`) : crate Rust *lmu-shared-memory* 0.1.0 (`src/lib.rs`, `src/shared_memory.rs`) : <https://docs.rs/lmu-shared-memory/0.1.0/lmu_shared_memory/>, <https://crates.io/crates/lmu-shared-memory>
- Emplacement des en-têtes dans le jeu (`Support/SharedMemoryInterface`), non redistribuables : README de *LmuOverlay* : <https://github.com/Pagh/LmuOverlay>
- Base historique rFactor 2 de la transcription TinyPedal : *pyRfactor2SharedMemory* : <https://github.com/TonyWhitley/pyRfactor2SharedMemory>

## À vérifier en jeu (Windows)

- Connexion réelle à `LMU_Data` avec la version installée (taille de la zone inchangée).
- `mSessionTimeRemaining` (propre à LMU) vs `mEndET - mCurrentET`, en particulier pour les courses au nombre de tours.
- `lap = mTotalLaps + 1` et `mLapNumber` cohérents avec l'affichage du jeu.
- Sens gauche/droite de `mTemperature` (intérieur/extérieur) sur une voiture au carrossage marqué.
- Sens de `mWear` : l'en-tête dit « fraction of maximum » ; on suppose 1,0 = neuf (convention habituelle rF2), à confirmer avec des pneus neufs puis usés.
- `mVirtualEnergy` : fraction 0-1 (d'après la transcription TinyPedal) et 0 sur les voitures sans énergie virtuelle (F02).
- `mMaxLaps` en course chronométrée (très grand nombre attendu) et `mInPits` pendant l'arrêt et la sortie des stands (F01).
- Libellés de `mVehicleClass` (Hypercar, LMP2, LMGT3 attendus) et présence du numéro `#7` dans `mVehicleName` (F07).
- Fréquence des lectures incohérentes (sans prise du verrou du jeu).
- Ordre de `mSectorFlag` (index 0 = secteur 3 supposé, comme `mSector`) et valeur d'un jaune local (1 supposé) (F10).
- API REST du jeu sur le port 6397 et format de `wearables` / `pitstop-estimate` (F11).
- Télémétrie des autres voitures : `mDentSeverity`, `mFuel`, `mVirtualEnergy` bien remplis pour les adversaires, en solo et en ligne (en ligne, le carburant des autres pourrait ne pas être transmis : « – » attendu).

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

Champs disponibles pour plus tard (déjà décrits dans les structures) : `mDeltaBest`, écarts `mTimeGapCarAhead/Behind`, météo (`mRaining`, `mAmbientTemp`, `mTrackTemp`, `mTrackGripLevel`), dégâts `mDentSeverity`, pédales, réglages TC/ABS, composés de pneus, secteurs, état des stands.

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
- Fréquence des lectures incohérentes (sans prise du verrou du jeu).

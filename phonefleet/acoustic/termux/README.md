# Scripts de déploiement autonome (téléphone / Termux)

Ces scripts permettent de **lancer une mission sans PC**. Ils s'exécutent
directement sur le Fairphone, dans Termux.

Le modèle d'IA reconnaît **4 classes** : petit bateau (< 50 m), bateau moyen
(50–100 m), grand bateau (> 100 m) et bruit de fond. Seules les 3 classes de
bateaux déclenchent des alertes.

## Données d'entraînement

Les données audio ne sont **pas** incluses dans ce dépôt (trop volumineuses).
Elles sont disponibles publiquement sur Zenodo :

👉 https://zenodo.org/records/15777429

Mise en place :

1. Télécharger l'archive depuis le lien ci-dessus et la décompresser
   (les fichiers audio et `iara.xlsx`).
2. Trier les fichiers par classe avec le script du projet :
Le modèle est entraîné sur le dataset **IARA** (enregistrements de navires).
`pc/prepare_training_data.py` trie les fichiers selon la longueur du navire, d'après
`iara.xlsx` :

```bash
python -m pc.prepare_training_data --xlsx iara.xlsx --source ./A ./B ./C --out ./training_data
```

Structure du dossier d'entraînement obtenue :

```
training_data/
├── small/        *.wav  (petits bateaux, < 50 m)
├── medium/       *.wav  (bateaux moyens, 50–100 m)
├── large/        *.wav  (grands bateaux, > 100 m)
└── background/   *.wav  (bruit de fond)
```

> Un éventuel dossier `bio/` est **ignoré** par `train.py` (avertissement dans les
> logs) : la classe biologique n'est pas active (voir §5).


3. Entraîner le modèle :

```bash
python -m pc.train --data ./training_data --epochs 150 --out mlp_weights.npz
```

`train.py` sépare train/test **par fichier** (pas de fuite d'information),
rééquilibre les classes, applique un early stopping sur la balanced accuracy et
affiche précision / rappel / F1 et la matrice de confusion.

Puis renseigner `MODEL_WEIGHTS=mlp_weights.npz` dans `.env`.

--- 

## Installation (une fois)

```bash
# Copier le repo sur le téléphone (SFTP, git clone, ou câble) dans ~/pfe
pkg install python termux-api ffmpeg
pip install numpy scipy
cp .env.example .env          # puis renseigner ALERT_PHONE, etc.

# Installer les icônes Termux:Widget + le démarrage auto Termux:Boot
bash termux/install_shortcuts.sh
```

> Si le repo n'est pas dans `~/pfe`, exportez `PFE_REPO=/chemin/vers/pfe` avant
> de lancer les scripts (ou éditez la valeur par défaut).

## Lancer une mission

Trois façons, au choix :

1. **Icône Termux:Widget** (recommandé en mer) : ajouter le widget Termux à
   l'écran d'accueil, puis toucher :
   - `PFE_MENU` (recommandé) : menu Démarrer / État / Arrêter, puis choix du profil ;
   - `PFE_RESUME` : relance le dernier profil choisi, en un tap ;
   - `PFE_SIMPLE`, `PFE_ALERTE`, `PFE_ALLO_BRUIT`, `PFE_TOUTES_OPTIONS` : lancement direct d'un profil ;
   - `PFE_STATUS` : autonomie (MEMORY_LIMIT / BATTERY_LIMIT) ;
   - `PFE_STOP` : arrêt volontaire et définitif.
2. **Démarrage auto au boot** (Termux:Boot) : l'enregistrement redémarre seul au
   boot du téléphone, avec le profil `PFE_BOOT_PROFILE` (défaut `ALERTE`).
3. **Ligne de commande** dans Termux :
   ```bash
   ./termux/start_deployment_ALERTE.sh
   ```

Au lancement (hors boot), le script demande le **site**, le **piézo** et le
**numéro d'alerte**, affiche l'**autonomie** (MEMORY_LIMIT / BATTERY_LIMIT),
puis démarre `android.receiver` via le superviseur.

## Résilience

- `supervisor.sh` relance automatiquement le receiver en cas de crash ou de
  coupure de connexion (SSH / Tailscale), après 10 s.
- Le superviseur est détaché du terminal (`setsid nohup`) : fermer la session
  n'interrompt pas l'enregistrement.
- Un verrou `flock` garantit qu'une seule instance du superviseur tourne.
- Seul `stop.sh` (icône `PFE_STOP`) arrête définitivement : il pose le drapeau
  `~/.pfe_stop_requested`, respecté par le superviseur et par le receiver.

## Vérifier l'autonomie et l'état à tout moment

Pendant que l'enregistrement tourne :

```bash
./termux/status.sh        # MEMORY_LIMIT, BATTERY_LIMIT, date de récupération
./termux/pfe_status.sh    # statut condensé : état, profil, dernier cycle, batterie
```

## Les profils

| Script | SMS bateaux | SMS batterie | Appel | GPS | Statut local |
|---|:-:|:-:|:-:|:-:|:-:|
| `start_deployment_SIMPLE`         | – | – | – | – | ✓ |
| `start_deployment_ALERTE`         | ✓ | ✓ | – | – | ✓ |
| `start_deployment_ALLO_BRUIT`     | ✓ | ✓ | ✓ | – | ✓ |
| `start_deployment_TOUTES_OPTIONS` | ✓ | ✓ | ✓ | ✓ | ✓ |

- Dès `ALERTE`, les 3 classes de bateaux envoient un SMS (seuil `MIN_CONFIDENCE`,
  anti-spam `COOLDOWN_MINUTES`).
- `ALLO_BRUIT` ajoute un **appel téléphonique** sur détection de forte confiance,
  avec un seuil et un anti-spam propres, plus stricts que ceux du SMS
  (`CALL_MIN_CONFIDENCE`, `CALL_COOLDOWN_MINUTES`).
- `TOUTES_OPTIONS` ajoute la lecture GPS à chaque cycle.
- Batterie : alerte « faible » (un seul SMS sous `BATTERY_VOLTAGE_THRESHOLD_MV`)
  et alerte « critique » (SMS répété avec position GPS sous `CRITICAL_BATTERY_PCT`).

Chaque option reste surchargeable via `.env` ou variable d'environnement
(ex. `ENABLE_GPS=1 ./termux/start_deployment_ALERTE.sh`).
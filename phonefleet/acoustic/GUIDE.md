# Guide pratique — Surveillance bioacoustique sous-marine

Guide d'exploitation du projet PFE : capture acoustique autonome sur Fairphone (Termux),
transfert SFTP vers PC, classification IA et dashboard.

> **Pour la personne qui reçoit ce projet** : ce guide te permet de tout installer,
> configurer et tester de bout en bout, **même sans le Fairphone** (grâce aux données
> de démo et à un WAV de test).

---

## 1. Prérequis

| Côté | Logiciel |
|------|----------|
| **PC** (Windows / Linux / Mac) | Python 3.10 → 3.14 |
| **Fairphone** (optionnel pour tester) | Termux + Termux:API (+ Termux:Widget et Termux:Boot pour le mode autonome) |

> Testé avec Python 3.14 + numpy 2.4 + scipy 1.17 + matplotlib 3.11.

---

## 2. Installation (côté PC)

```bash
# 1. Se placer à la racine du projet
cd pfe_ref

# 2. Installer les dépendances
pip install numpy scipy matplotlib paramiko

# Seulement si tu prépares le dataset IARA (pc/prepare_training_data.py) :
pip install openpyxl

# (librosa, listé dans requirements.txt, n'est PAS utilisé par le code actuel —
#  inutile de l'installer, surtout sur Python 3.14)

# 3. Créer le fichier de configuration
cp .env.example .env        # Windows PowerShell : copy .env.example .env
```

Puis ouvrir `.env` et renseigner au minimum (uniquement si tu utilises un vrai Fairphone) :

```ini
PHONE_IP=192.168.1.100      # IP du téléphone sur le réseau
SSH_USER=u0_a236            # donné par la commande `whoami` dans Termux
SSH_PASSWORD=...            # mot de passe SSH Termux
SITE=banyuls                # nom du site de mesure
ALERT_PHONE=+33XXXXXXXXX    # numéro qui reçoit les alertes SMS / appels
```

> ⚠️ Le `.env` contient des secrets (mot de passe SSH). **Ne jamais le partager / committer.**
> Il est déjà ignoré par `.gitignore`.

---

## 3. Test rapide SANS Fairphone (recommandé en premier)

Tu peux valider toute la chaîne de traitement sur PC, sans téléphone.

### 3.1 Générer un vrai fichier WAV de test

Les WAV de démo (`recordings/...`) sont des fichiers **vides** (octets nuls) : ils servent
uniquement au dashboard, **pas** à l'analyse audio. Pour tester l'audio, crée un vrai WAV :

```bash
python -c "import numpy as np,scipy.io.wavfile as w; sr=44100; t=np.linspace(0,3,sr*3,endpoint=False); x=0.3*np.sin(2*np.pi*200*t)+0.05*np.random.randn(len(t)); w.write('test_real.wav',sr,(x*32767).astype(np.int16))"
```

→ crée `test_real.wav` (3 s, ton 200 Hz + bruit).

### 3.2 Tester l'IA sur ce fichier

```bash
python -m pc.detect_cli --wav test_real.wav
```

Résultat attendu (poids **non entraînés** → probabilités ~uniformes) :

```json
{ "class_name": "...", "confidence": 0.25, "file_ratio": 1.0, "alert": false }
```

> `confidence ≈ 0.25` est normal sans modèle entraîné (1/4 classes). C'est un test de
> plomberie, pas une vraie détection.

### 3.3 Tester l'analyse spectrale (spectrogramme + PSD)

```bash
python -m pc.analyze --wav test_real.wav --out test_analyse
```

→ produit dans `test_analyse/` : `spectrogram.png`, `psd.png`, `events.csv`, `summary.json`.
Ouvre `psd.png` : tu dois voir un **pic net à 200 Hz**.

### 3.4 Tester le dashboard (avec les données de démo)

```bash
python -m pc.dashboard --data recordings --out .
```

→ génère `dashboard.html` (+ `dashboard.csv`). Ouvre `dashboard.html` dans un navigateur.

Version live (rafraîchissement auto + serveur local) :

```bash
python -m pc.dashboard --data recordings --live
```

### 3.5 Tester l'alerte SMS (mode simulation)

Hors Termux, les SMS sont seulement **affichés** dans la console (aucun envoi réel) :

```bash
python -m pc.detect_cli --wav test_real.wav --threshold 0.1 --sms
```

→ affiche `[SIMULATION SMS] ...`. Un 2ᵉ appel immédiat est bloqué par le cooldown anti-spam.

### 3.6 Regénérer les données de démo (dashboard)

```bash
python tests/make_demo_data.py --clean
```

→ recrée des enregistrements de démo (sites `sete` + `banyuls`), pour le dashboard.

---

## 4. Utilisation réelle AVEC le Fairphone

### 4.1 Préparer le Fairphone (Termux)

```bash
pkg update && pkg install python termux-api openssh ffmpeg
pip install numpy scipy
sshd                          # démarre le serveur SSH (port 8022)
whoami                        # donne le SSH_USER (ex. u0_a236)
```

`ffmpeg` est indispensable : `termux-microphone-record` produit de l'AAC/M4A, que le
receiver convertit en WAV PCM.

**Permissions Android** à accorder à Termux:API (Paramètres → Applications) :
micro, SMS, téléphone (pour l'appel du profil ALLO_BRUIT), localisation (GPS).

Vérifier que les commandes Termux:API répondent :
`termux-microphone-record`, `termux-location`, `termux-battery-status`,
`termux-sms-send`, `termux-telephony-call`.

### 4.2 Déployer et lancer (depuis le PC)

```bash
# Terminal 1 — déploie le code sur le téléphone + démarre l'enregistrement
python -m pc.launch

# Terminal 2 — récupère les WAV+métadonnées en boucle + lance l'analyse
python -m pc.collect

# Terminal 3 — dashboard live
python -m pc.dashboard --data recordings --live
```

> **Collecte limitée au site Banyuls** : `pc/collect.py` lit uniquement
> `<données>/banyuls/AAAA/MM/JJ/` (constante `SITE`). Pour un autre site, modifier
> cette constante.
>
> Pour ne collecter qu'à partir d'une date (et heure) donnée :
> `python -m pc.collect --depuis 2026-07-20` ou `--depuis 2026-07-20T14:30`.
> Option `--once` : une seule passe, sans boucle.

### 4.3 Déploiement AUTONOME sur le téléphone (sans PC en mer)

C'est le mode d'exploitation réel : le Fairphone tourne seul du début à la fin.

**Installation sur le téléphone (une fois)** — copier le repo dans `~/pfe` puis :

```bash
pkg install python termux-api openssh ffmpeg
pip install numpy scipy
cp .env.example .env          # renseigner ALERT_PHONE (et PHONE_HOST si post-traitement)
bash termux/install_shortcuts.sh   # crée les icônes Termux:Widget + le boot auto
```

> Installer aussi les apps **Termux:Widget** et **Termux:Boot** (F-Droid) pour les
> icônes d'écran d'accueil et le démarrage automatique.

**Lancer une mission** — trois façons :

1. **Icône Termux:Widget** (recommandé) :
   - `PFE_MENU` : menu Démarrer / État / Arrêter, puis choix du profil ;
   - `PFE_RESUME` : relance le dernier profil choisi ;
   - `PFE_SIMPLE`, `PFE_ALERTE`, `PFE_ALLO_BRUIT`, `PFE_TOUTES_OPTIONS` : profil direct ;
   - `PFE_STATUS` : autonomie ; `PFE_STOP` : arrêt définitif.
2. **Boot automatique** : au redémarrage du téléphone, l'enregistrement reprend
   seul (profil `PFE_BOOT_PROFILE`, défaut `ALERTE`). Le site/piézo doivent déjà
   être dans `.env` (lancer une fois un profil interactif avant).
3. **Ligne de commande** : `./termux/start_deployment_ALERTE.sh`.

Au lancement (hors boot), le script demande le **site**, le **piézo** et le
**numéro d'alerte**, affiche l'**autonomie**, puis démarre `android.receiver`
via le superviseur.

**Résilience** : `termux/supervisor.sh` relance le receiver après un crash ou une
coupure de connexion (10 s), reste actif si la session SSH se ferme, et un verrou
`flock` empêche deux instances. Seul `PFE_STOP` (`termux/stop.sh`) arrête
définitivement.

**Les profils** :

| Profil | SMS bateaux | SMS batterie | Appel | GPS | Statut local |
|---|:-:|:-:|:-:|:-:|:-:|
| SIMPLE         | – | – | – | – | ✓ |
| ALERTE         | ✓ | ✓ | – | – | ✓ |
| ALLO_BRUIT     | ✓ | ✓ | ✓ | – | ✓ |
| TOUTES_OPTIONS | ✓ | ✓ | ✓ | ✓ | ✓ |

Dès `ALERTE`, les 3 classes de bateaux envoient un SMS (seuil `MIN_CONFIDENCE`,
anti-spam `COOLDOWN_MINUTES`). `ALLO_BRUIT` ajoute un **appel téléphonique** sur
détection de forte confiance, avec un seuil et un anti-spam propres, plus stricts
(`CALL_MIN_CONFIDENCE`, `CALL_COOLDOWN_MINUTES`). `TOUTES_OPTIONS` ajoute la
lecture GPS à chaque cycle. Chaque option reste surchargeable via `.env`
(ex. `ENABLE_GPS=1`).

**Alertes batterie** : « faible » (un seul SMS sous `BATTERY_VOLTAGE_THRESHOLD_MV`)
et « critique » (SMS répété avec position GPS sous `CRITICAL_BATTERY_PCT`).

### 4.4 Vérifier l'autonomie à tout moment (MEMORY_LIMIT / BATTERY_LIMIT)

Commande indépendante, sûre même pendant que `receiver` tourne en arrière-plan :

```bash
./termux/status.sh            # ou : python -m android.status
./termux/pfe_status.sh        # statut condensé (état, profil, dernier cycle)
```

```
-------- Autonomie du deploiement --------
  MEMORY_LIMIT  = 5.1 j   (disque libre 19.5 Go, 720 cycles/j, 5.3 Mo/cycle)
  BATTERY_LIMIT = 2.8 j   (batterie 71%, estimation observé)
  -> Recuperer l'appareil avant : 04/07 08:12 (contrainte : batterie)
```

- **MEMORY_LIMIT** : espace disque libre ÷ (taille d'un cycle × cycles/jour).
- **BATTERY_LIMIT** : niveau actuel ÷ consommation. Si le téléphone est **en
  charge/sur secteur** → `no` (illimité).
- **Estimation batterie — hybride** : au départ, la consommation calibrée
  `BATTERY_DRAIN_PCT_PER_DAY` (%/jour) sert de base ; après ~2 h et ≥3 % de
  décharge, l'estimation bascule automatiquement sur le **taux réellement observé
  depuis le début de la mission** (mention « observé »). C'est plus réactif au
  froid ou à l'usage GPS qu'une constante figée, sans le bruit des premières minutes.

**Calibrer `BATTERY_DRAIN_PCT_PER_DAY`** (une fois, pour de bons chiffres au
démarrage) : lancer un profil représentatif sur batterie, noter le % au début et
après ~2–3 h, puis `%/jour = (pct_debut − pct_fin) × 24 / heures`. Reporter la
valeur dans `.env`. Ensuite l'estimation observée prend le relais d'elle-même.

### 4.5 Retrouver le téléphone depuis le PC (IP stable, post-traitement)

L'IP DHCP change à chaque connexion : ne jamais s'y fier. `PHONE_HOST` accepte un
identifiant stable (utilisé seulement pour `pc.collect`/`pc.dashboard`/`pc.launch`,
pas pour l'enregistrement) :

| Option | Portée | Remarque |
|---|---|---|
| **Tailscale** (recommandé) | N'importe quel réseau / 4G | IP `100.x` ou nom MagicDNS fixe. Idéal au retour au port. Nécessite l'app + un compte. |
| **mDNS `.local`** | Même Wi-Fi | `fairphone.local` (paquet `avahi`). Simple, sans compte ; support Android parfois capricieux. |
| **Réservation DHCP** | Un réseau précis | IP fixe sur la box. Fiable mais non portable. |
| **DNS dynamique** | Internet | Suit l'IP publique ; nécessite port-forwarding, KO derrière 4G/CGNAT. |

**Mise en place Tailscale** (une fois) :

```bash
# Sur le téléphone : installer l'app Tailscale (Play Store / F-Droid), se connecter,
# noter le nom de machine (ex. "fairphone").
# Sur le PC : installer Tailscale, se connecter au même compte.
```

Puis dans `.env` : `PHONE_HOST=fairphone` (ou l'IP `100.x`). `ssh_client` l'utilise
automatiquement, avec repli sur `PHONE_IP`.

## 4.6 Données d'entraînement

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

## 5. Les classes du modèle

| ID | Classe | Alerte SMS |
|----|---------------------------|:-:|
| 0 | Petit bateau (< 50 m) | oui |
| 1 | Bateau moyen (50–100 m) | oui |
| 2 | Grand bateau (> 100 m) | oui |
| 3 | Bruit de fond | non |

Le modèle a donc **4 sorties**. `MLP.load()` refuse un fichier de poids dont le
nombre de classes ne correspond pas.

### Perspectives

- **Classe biologique (poissons)** : volontairement retirée faute de données
  annotées fiables. Elle pourra être ajoutée quand un jeu de données poissons sera
  disponible (il faudra mettre à jour `CLASSES` et `ALERT_CLASSES` dans
  `core/model.py`, et `CLASS_MAP` dans `pc/train.py`).

---

## 6. Dépannage (FAQ)

| Symptôme | Cause / Solution |
|----------|------------------|
| `ModuleNotFoundError: scipy` (ou matplotlib, paramiko) | `pip install scipy matplotlib paramiko` |
| `ValueError: File format ... not understood` | Tu analyses un WAV de démo (vide). Utilise un **vrai** WAV (§3.1). |
| `Logging error ... UnicodeEncodeError` (console Windows) | Cosmétique : l'analyse réussit quand même. Lance `set PYTHONUTF8=1` avant la commande pour supprimer le message. |
| `Clé manquante dans .env` | Crée le `.env` à partir de `.env.example`. |
| `PHONE_HOST (ou PHONE_IP) manquant` au `launch` | Renseigne `PHONE_IP` (ou `PHONE_HOST`) dans `.env`. |
| SSH échoue | Vérifie que `sshd` tourne dans Termux et que PC + téléphone sont sur le **même réseau** (ou via Tailscale). |
| Dashboard vide | Vérifie que `recordings/` contient des `log_*.txt`. Sinon : `python tests/make_demo_data.py`. |
| Aucun WAV créé sur le téléphone | Vérifie que `ffmpeg` est installé et que la permission micro est accordée. |
| Pas d'appel / de SMS reçu | Vérifie les permissions SMS et téléphone de Termux:API, et le profil actif (`ALERTE` pour SMS, `ALLO_BRUIT` pour appel). |
| Le receiver ne redémarre pas après `PFE_STOP` | Normal : l'arrêt est définitif. Relancer via `PFE_MENU` ou `PFE_RESUME`. |

---

## 7. Limitations connues (à garder en tête)

- Les **WAV de démo sont vides** : utiles seulement pour le dashboard, pas pour l'IA.
- Les **poids du modèle sont aléatoires** tant que `MODEL_WEIGHTS` n'est pas défini :
  les détections ne sont pas fiables avant entraînement.
- Le **cooldown SMS / appel** est par classe et en mémoire (réinitialisé au redémarrage).
- `pc/collect.py` ne collecte que le site **Banyuls** (constante `SITE`).
- `openpyxl` n'est nécessaire que pour `pc/prepare_training_data.py`.
- Le modèle ne distingue que des **bateaux par taille** et le bruit de fond ; il ne
  détecte pas les sons biologiques.

---

## 8. Structure du projet

```
pfe_ref/
├── .env         # modèle de config 
├── requirements.txt
├── GUIDE.md              # ce guide
├── core/                 # bibliothèque partagée Android + PC
│   ├── config.py  audio.py  spectral.py  model.py  detector.py
│   ├── alert.py  autonomy.py  metadata.py  logging_utils.py
├── android/              # scripts Fairphone (Termux)
│   ├── receiver.py  setup.py  status.py  pretty_status.py
│   ├── dashboard.py  analyze_cli.py
├── pc/                   # scripts PC
│   ├── launch.py  collect.py  ssh_client.py
│   ├── analyze.py  dashboard.py  detect_cli.py
│   ├── train.py  prepare_training_data.py
├── termux/               # scripts shell de pilotage (téléphone)
│   ├── supervisor.sh  start_deployment.sh  start_deployment_<PROFIL>.sh
│   ├── deploy_menu.sh  resume.sh  stop.sh
│   ├── status.sh  pfe_status.sh  install_shortcuts.sh
│   ├── boot/start_pfe_boot.sh
│   └── README.md
├── templates/dashboard.html
├── tests/make_demo_data.py
└── recordings/           # données (démo ou réelles)
```
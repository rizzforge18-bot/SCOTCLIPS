# SCOTCLIPS — Bot Telegram perso de découpage de clips

## Installation

```bash
pip install -r requirements.txt
```

Il faut aussi `ffmpeg` installé sur la machine :
```bash
# Sur Railway : ajoute un buildpack/nixpacks avec ffmpeg, ou utilise une image Docker qui l'inclut déjà
apt-get install ffmpeg   # en local sur Ubuntu/Debian
```

## Configuration

Le fichier `.env` est déjà rempli avec ton token Telegram SCOTCLIPS. Il te reste
à ajouter ta clé OpenRouter :

```
OPENROUTER_API_KEY=sk-or-v1-...
```

## Lancer le bot

```bash
python bot.py
```

Le bot tourne en polling — pas besoin de webhook pour un usage perso.
Pour le faire tourner en continu sur Railway, déploie ce dossier comme
un service, avec `python bot.py` en start command et les variables du
`.env` en variables d'environnement Railway.

## Utilisation

- `/start` (ou bouton "🏠 Start" en bas) — menu d'accueil
- Envoie un lien vidéo (YouTube, TikTok, Instagram, etc.) — le bot télécharge,
  transcrit, détecte jusqu'à 10 moments forts, découpe et sous-titre
- Chaque clip est envoyé avec une note de viralité /10 et sa justification
- Bouton "📊 Bilan" — historique de toutes les vidéos traitées, total de clips,
  top 5 des clips les mieux notés

## Structure

| Fichier | Rôle |
|---|---|
| `bot.py` | Bot Telegram (menu, handlers, envoi des clips) |
| `transcribe.py` | Téléchargement (yt-dlp) + transcription mot-par-mot (faster-whisper) |
| `highlight_detector.py` | Détection des moments forts + note de viralité via OpenRouter |
| `generate_subtitles.py` | Génère les sous-titres animés mot-par-mot (.ass) |
| `pipeline.py` | Orchestre tout : lien -> clips finis |
| `stats.json` | Généré automatiquement, historique pour le Bilan |

## Réglages rapides

- **Modèle Whisper** : `WHISPER_MODEL_SIZE` dans `.env` (`tiny`/`base`/`small`/`medium`/`large-v3`) —
  plus gros = plus précis mais plus lent/coûteux en RAM
- **Style des sous-titres** : couleurs/police en haut de `generate_subtitles.py`
  (`HIGHLIGHT_COLOR`, `FONT_NAME`, `FONT_SIZE`)
- **Nombre de clips / durée** : `MAX_HIGHLIGHTS`, `MIN_CLIP_SECONDS`, `MAX_CLIP_SECONDS`
  en haut de `highlight_detector.py`

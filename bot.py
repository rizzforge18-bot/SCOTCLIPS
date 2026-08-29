"""
bot.py — SCOTCLIPS

Bot Telegram perso : envoie un lien vidéo, le bot télécharge, transcrit,
détecte jusqu'à 10 moments forts (notés /10 sur leur potentiel de
viralité), découpe les clips et incruste des sous-titres animés.

Usage:
    python bot.py

Variables d'environnement requises (mets-les dans un fichier .env, voir
.env.example) :
    TELEGRAM_BOT_TOKEN
    OPENROUTER_API_KEY
"""

import json
import os
import shutil
import tempfile
import traceback
from datetime import datetime

from dotenv import load_dotenv
from telegram import ReplyKeyboardMarkup, Update, InputFile
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from pipeline import full_pipeline

load_dotenv()

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
STATS_FILE = os.path.join(os.path.dirname(__file__), "stats.json")

# --- Menu persistant (toujours visible en bas du clavier Telegram) ---
MAIN_MENU = ReplyKeyboardMarkup(
    [
        ["🎬 Nouveau clip"],
        ["📊 Bilan", "🏠 Start"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)


# ---------- Stats / bilan ----------

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"videos_traitees": 0, "clips_generes": 0, "clips": []}


def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def record_run(results, source_url):
    stats = load_stats()
    stats["videos_traitees"] += 1
    stats["clips_generes"] += len(results)
    for r in results:
        stats["clips"].append({
            "title": r.get("title"),
            "virality_score": r.get("virality_score"),
            "date": datetime.now().isoformat(timespec="seconds"),
            "source_url": source_url,
        })
    save_stats(stats)
    return stats


# ---------- Handlers ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎬 *SCOTCLIPS*\n\n"
        "Envoie-moi un lien de vidéo (YouTube, TikTok, Instagram...) et je te renvoie "
        "jusqu'à 10 clips, sous-titrés et notés sur 10 selon leur potentiel de viralité.\n\n"
        "Utilise le menu en bas à tout moment.",
        parse_mode="Markdown",
        reply_markup=MAIN_MENU,
    )


async def bilan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = load_stats()
    if not stats["clips"]:
        await update.message.reply_text(
            "Aucun clip généré pour l'instant. Envoie un lien pour commencer 🎬",
            reply_markup=MAIN_MENU,
        )
        return

    top5 = sorted(stats["clips"], key=lambda c: c.get("virality_score") or 0, reverse=True)[:5]
    top_text = "\n".join(
        f"  {i}. {c['title']} — {c['virality_score']}/10" for i, c in enumerate(top5, 1)
    )

    text = (
        f"📊 *Bilan SCOTCLIPS*\n\n"
        f"Vidéos traitées : {stats['videos_traitees']}\n"
        f"Clips générés : {stats['clips_generes']}\n\n"
        f"🏆 Top 5 clips (viralité) :\n{top_text}"
    )
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=MAIN_MENU)


async def prompt_new_clip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Envoie-moi directement le lien de la vidéo à découper 👇",
        reply_markup=MAIN_MENU,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if text in ("🎬 Nouveau clip",):
        return await prompt_new_clip(update, context)
    if text in ("📊 Bilan",):
        return await bilan(update, context)
    if text in ("🏠 Start",):
        return await start(update, context)

    if not text.startswith("http"):
        await update.message.reply_text(
            "Envoie-moi un lien vidéo valide (http...), ou utilise le menu en bas.",
            reply_markup=MAIN_MENU,
        )
        return

    await process_link(update, context, text)


async def process_link(update: Update, context: ContextTypes.DEFAULT_TYPE, url: str):
    status_msg = await update.message.reply_text("⏳ Téléchargement et transcription en cours...")
    work_dir = tempfile.mkdtemp(prefix="scotclips_")

    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.RECORD_VIDEO)
        results = full_pipeline(url, work_dir)

        if not results:
            await status_msg.edit_text("Aucun moment fort détecté dans cette vidéo. Essaie un autre lien.")
            return

        await status_msg.edit_text(f"✅ {len(results)} clips prêts. Envoi en cours...")

        for r in sorted(results, key=lambda x: x.get("virality_score") or 0, reverse=True):
            caption = (
                f"🔥 *{r.get('title', 'Clip')}* ({r.get('format', '')})\n"
                f"Viralité : *{r.get('virality_score')}/10*\n"
                f"{r.get('reason', '')}"
            )
            with open(r["file"], "rb") as video_file:
                await context.bot.send_video(
                    chat_id=update.effective_chat.id,
                    video=InputFile(video_file),
                    caption=caption,
                    parse_mode="Markdown",
                )

        record_run(results, url)
        await update.message.reply_text("📊 Tape 'Bilan' pour voir tes stats globales.", reply_markup=MAIN_MENU)

    except Exception as e:
        traceback.print_exc()
        await status_msg.edit_text(f"❌ Erreur pendant le traitement : {e}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)


def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("bilan", bilan))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("SCOTCLIPS démarré...")
    app.run_polling()


if __name__ == "__main__":
    main()

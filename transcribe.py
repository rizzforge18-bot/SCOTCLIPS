"""
transcribe.py

Télécharge une vidéo depuis un lien (YouTube, TikTok, Instagram, etc. -
tout ce que yt-dlp supporte) et génère sa transcription avec timestamps
mot-par-mot via faster-whisper.

Usage:
    python transcribe.py "https://..." output_dir/

Produit dans output_dir/:
    - video.mp4
    - transcript.json   (format attendu par highlight_detector.py et generate_subtitles.py)
"""

import json
import os
import sys

import yt_dlp
from faster_whisper import WhisperModel

WHISPER_MODEL_SIZE = os.environ.get("WHISPER_MODEL_SIZE", "medium")
WHISPER_DEVICE = os.environ.get("WHISPER_DEVICE", "cpu")  # "cuda" si GPU dispo
WHISPER_COMPUTE_TYPE = os.environ.get("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_LANGUAGE = os.environ.get("WHISPER_LANGUAGE", "fr")


def download_video(url, output_dir):
    video_path = os.path.join(output_dir, "video.mp4")
    ydl_opts = {
        "outtmpl": video_path,
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {"player_client": ["web", "android"]}
        },
    }

    cookies_content = os.environ.get("YTDLP_COOKIES_TXT")
    if cookies_content:
        cookies_path = os.path.join(output_dir, "cookies.txt")
        with open(cookies_path, "w", encoding="utf-8") as f:
            f.write(cookies_content)
        ydl_opts["cookiefile"] = cookies_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return video_path, info.get("title", "video")


def transcribe(video_path):
    model = WhisperModel(WHISPER_MODEL_SIZE, device=WHISPER_DEVICE, compute_type=WHISPER_COMPUTE_TYPE)
    segments_iter, info = model.transcribe(
        video_path,
        language=WHISPER_LANGUAGE,
        word_timestamps=True,
        vad_filter=True,
    )

    segments = []
    for seg in segments_iter:
        words = [
            {"word": w.word, "start": w.start, "end": w.end}
            for w in (seg.words or [])
        ]
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text,
            "words": words,
        })

    return {"language": info.language, "duration": info.duration, "segments": segments}


def run(url, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    print("1/2 - Téléchargement de la vidéo...")
    video_path, title = download_video(url, output_dir)

    print("2/2 - Transcription (faster-whisper)...")
    transcript = transcribe(video_path)
    transcript["title"] = title

    transcript_path = os.path.join(output_dir, "transcript.json")
    with open(transcript_path, "w", encoding="utf-8") as f:
        json.dump(transcript, f, ensure_ascii=False, indent=2)

    print(f"OK -> {video_path}, {transcript_path}")
    return video_path, transcript_path


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print('Usage: python transcribe.py "https://..." output_dir/')
        sys.exit(1)

    run(sys.argv[1], sys.argv[2])

"""
pipeline.py

Orchestration complète : vidéo source + transcript.json (déjà généré par
ton bot Whisper) -> clips finis avec sous-titres animés incrustés.

Usage:
    python pipeline.py video.mp4 transcript.json output_dir/

Prérequis:
    pip install requests
    ffmpeg installé sur la machine (Railway image doit l'inclure)
    variable d'env OPENROUTER_API_KEY définie

Étapes:
    1. highlight_detector.py -> identifie les meilleurs segments
    2. ffmpeg -> découpe chaque segment de la vidéo source
    3. generate_subtitles.py -> génère le .ass pour ce segment
    4. ffmpeg -> incruste les sous-titres dans le clip découpé
"""

import json
import os
import subprocess
import sys

from highlight_detector import detect_highlights
from generate_subtitles import generate as generate_subtitles
from transcribe import run as transcribe_url


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Commande échouée: {' '.join(cmd)}\n{result.stderr}")
    return result.stdout


def cut_clip(video_path, start, end, out_path):
    run([
        "ffmpeg", "-y",
        "-i", video_path,
        "-ss", str(start),
        "-to", str(end),
        "-c:v", "libx264", "-c:a", "aac",
        "-preset", "fast",
        out_path,
    ])


def burn_subtitles(clip_path, ass_path, out_path):
    run([
        "ffmpeg", "-y",
        "-i", clip_path,
        "-vf", f"ass={ass_path}",
        "-c:a", "copy",
        out_path,
    ])


def slugify(text, max_len=40):
    keep = "".join(c if c.isalnum() or c in " -_" else "" for c in text)
    return keep.strip().replace(" ", "_")[:max_len] or "clip"


def process(video_path, transcript_path, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    print("1/4 - Détection des highlights via OpenRouter...")
    highlights = detect_highlights(transcript_path)
    print(f"   -> {len(highlights)} moments identifiés")

    results = []
    for i, h in enumerate(highlights, start=1):
        name = slugify(h.get("title", f"clip_{i}"))
        raw_clip = os.path.join(output_dir, f"{i}_{name}_raw.mp4")
        ass_file = os.path.join(output_dir, f"{i}_{name}.ass")
        final_clip = os.path.join(output_dir, f"{i}_{name}.mp4")

        print(f"2/4 - Découpage clip {i} ({h['start']:.1f}s -> {h['end']:.1f}s)...")
        cut_clip(video_path, h["start"], h["end"], raw_clip)

        print(f"3/4 - Génération sous-titres clip {i}...")
        generate_subtitles(transcript_path, h["start"], h["end"], ass_file)

        print(f"4/4 - Incrustation sous-titres clip {i}...")
        burn_subtitles(raw_clip, ass_file, final_clip)

        os.remove(raw_clip)  # on garde que la version finale
        results.append({
            "file": final_clip,
            "title": h.get("title"),
            "reason": h.get("reason"),
            "virality_score": h.get("virality_score"),
        })

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nTerminé. {len(results)} clips prêts dans {output_dir}")
    return results


def full_pipeline(url, work_dir):
    """Point d'entrée unique pour le bot : lien -> clips finis.
    Enchaîne téléchargement, transcription, détection des highlights,
    découpage et incrustation des sous-titres."""
    video_path, transcript_path = transcribe_url(url, work_dir)
    return process(video_path, transcript_path, work_dir)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python pipeline.py video.mp4 transcript.json output_dir/")
        sys.exit(1)

    process(sys.argv[1], sys.argv[2], sys.argv[3])

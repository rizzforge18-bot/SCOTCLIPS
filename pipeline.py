"""
pipeline.py

Orchestration complete : video source + transcript.json (deja genere par
ton bot Whisper) -> clips finis, recadres en 1:1 et 9:16 en suivant le
visage qui parle, avec sous-titres modernes incrustes.

Usage:
    python pipeline.py video.mp4 transcript.json output_dir/

Prerequis:
    pip install -r requirements.txt
    ffmpeg installe sur la machine (Railway image doit l'inclure)
    variable d'env OPENROUTER_API_KEY definie

Etapes par highlight detecte :
    1. Decoupage du segment brut (aspect original)
    2. Recadrage intelligent (suivi de visage) en 1:1 et en 9:16
    3. Generation des sous-titres adaptes a chaque format
    4. Incrustation des sous-titres sur chaque version
"""

import json
import os
import subprocess
import sys

from highlight_detector import detect_highlights
from generate_subtitles import generate as generate_subtitles
from transcribe import run as transcribe_url
from reframe import reframe

FORMATS = ["9:16", "1:1"]


def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Commande echouee: {' '.join(cmd)}\n{result.stderr}")
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

    print("1/4 - Detection des highlights via OpenRouter...")
    highlights = detect_highlights(transcript_path)
    print(f"   -> {len(highlights)} moments identifies")

    results = []
    for i, h in enumerate(highlights, start=1):
        name = slugify(h.get("title", f"clip_{i}"))
        raw_clip = os.path.join(output_dir, f"{i}_{name}_raw.mp4")

        print(f"2/4 - Decoupage clip {i} ({h['start']:.1f}s -> {h['end']:.1f}s)...")
        cut_clip(video_path, h["start"], h["end"], raw_clip)

        for fmt in FORMATS:
            fmt_tag = fmt.replace(":", "x")
            reframed_path = os.path.join(output_dir, f"{i}_{name}_{fmt_tag}_raw.mp4")
            ass_file = os.path.join(output_dir, f"{i}_{name}_{fmt_tag}.ass")
            final_clip = os.path.join(output_dir, f"{i}_{name}_{fmt_tag}.mp4")

            print(f"3/4 - Recadrage {fmt} (suivi du visage) clip {i}...")
            _, out_w, out_h = reframe(raw_clip, reframed_path, fmt)

            print(f"4/4 - Sous-titres + incrustation {fmt} clip {i}...")
            generate_subtitles(transcript_path, h["start"], h["end"], ass_file, out_w, out_h)
            burn_subtitles(reframed_path, ass_file, final_clip)

            os.remove(reframed_path)

            results.append({
                "file": final_clip,
                "format": fmt,
                "title": h.get("title"),
                "reason": h.get("reason"),
                "virality_score": h.get("virality_score"),
            })

        os.remove(raw_clip)

    manifest_path = os.path.join(output_dir, "manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\nTermine. {len(results)} fichiers prets dans {output_dir}")
    return results


def full_pipeline(url, work_dir):
    """Point d'entree unique pour le bot : lien -> clips finis.
    Enchaine telechargement, transcription, detection des highlights,
    decoupage, recadrage intelligent (1:1 + 9:16) et incrustation des sous-titres."""
    video_path, transcript_path = transcribe_url(url, work_dir)
    return process(video_path, transcript_path, work_dir)


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python pipeline.py video.mp4 transcript.json output_dir/")
        sys.exit(1)

    process(sys.argv[1], sys.argv[2], sys.argv[3])

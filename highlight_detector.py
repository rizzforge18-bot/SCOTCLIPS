"""
highlight_detector.py

Prend la sortie JSON de faster-whisper (segments + mots avec timestamps)
et demande à un LLM (via OpenRouter) d'identifier 3 à 5 moments à fort
potentiel viral, avec leurs timestamps de début/fin.

Usage:
    python highlight_detector.py transcript.json

Entrée attendue (transcript.json) — format faster-whisper typique:
{
  "segments": [
    {
      "start": 12.34,
      "end": 15.80,
      "text": "...",
      "words": [{"word": "salut", "start": 12.34, "end": 12.60}, ...]
    },
    ...
  ]
}

Sortie: liste de highlights au format JSON, ex:
[
  {"start": 45.2, "end": 78.9, "title": "...", "reason": "..."},
  ...
]
"""

import json
import os
import sys
import re
import requests

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "anthropic/claude-sonnet-4.5")

MIN_CLIP_SECONDS = 15
MAX_CLIP_SECONDS = 90
MAX_HIGHLIGHTS = 10


def build_transcript_text(segments):
    """Reconstruit un texte horodaté lisible par le LLM, ex: [12.3s] texte..."""
    lines = []
    for seg in segments:
        lines.append(f"[{seg['start']:.1f}s -> {seg['end']:.1f}s] {seg['text'].strip()}")
    return "\n".join(lines)


def build_prompt(transcript_text):
    return f"""Tu es un expert en création de clips viraux pour Instagram Reels / TikTok / YouTube Shorts, spécialisé dans le contenu francophone (Haïti, Québec, France).

Voici la transcription horodatée d'une vidéo (format [début -> fin] texte) :

---
{transcript_text}
---

Identifie entre 3 et {MAX_HIGHLIGHTS} extraits à fort potentiel viral. Critères :
- Punchlines, révélations, moments choquants, drôles, ou émotionnellement forts
- Un début et une fin qui font sens seuls (hook clair, chute claire)
- Durée entre {MIN_CLIP_SECONDS} et {MAX_CLIP_SECONDS} secondes
- Les timestamps doivent correspondre EXACTEMENT à ceux fournis dans la transcription (ne pas inventer)
- Attribue à chaque extrait une note de viralité sur 10 (10 = extrêmement viral, 1 = faible potentiel), basée sur le hook, l'émotion, la surprise et la capacité à retenir l'attention dans les 3 premières secondes

Réponds UNIQUEMENT avec un JSON valide, sans texte autour, sans balises markdown, au format :
[
  {{"start": <float>, "end": <float>, "title": "<titre accrocheur court>", "reason": "<pourquoi ce moment est fort, 1 phrase>", "virality_score": <int 1-10>}}
]
"""


def call_openrouter(prompt):
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY manquant dans l'environnement")

    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
        },
        timeout=120,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def extract_json(raw_text):
    """Le LLM peut parfois entourer le JSON de ```json ... ``` malgré la consigne."""
    cleaned = re.sub(r"^```(json)?|```$", "", raw_text.strip(), flags=re.MULTILINE).strip()
    return json.loads(cleaned)


def detect_highlights(transcript_path):
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    segments = transcript["segments"]
    transcript_text = build_transcript_text(segments)
    prompt = build_prompt(transcript_text)

    raw_response = call_openrouter(prompt)
    highlights = extract_json(raw_response)

    # Sécurité : borne les durées au cas où le LLM dérape
    valid = []
    for h in highlights:
        duration = h["end"] - h["start"]
        if MIN_CLIP_SECONDS * 0.5 <= duration <= MAX_CLIP_SECONDS * 1.5:
            h["virality_score"] = max(1, min(10, int(h.get("virality_score", 5))))
            valid.append(h)

    valid.sort(key=lambda h: h["virality_score"], reverse=True)
    return valid[:MAX_HIGHLIGHTS]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python highlight_detector.py transcript.json")
        sys.exit(1)

    highlights = detect_highlights(sys.argv[1])
    print(json.dumps(highlights, ensure_ascii=False, indent=2))

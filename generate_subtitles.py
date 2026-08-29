"""
generate_subtitles.py

Génère un fichier sous-titres .ass avec animation mot-par-mot
(style Opus Clip / CapCut : chaque mot en surbrillance au moment
où il est prononcé), à partir des timestamps mots de faster-whisper.

Usage:
    python generate_subtitles.py transcript.json 45.2 78.9 output.ass
    (transcript.json = sortie whisper complète, 45.2/78.9 = début/fin du clip en secondes)

Le fichier .ass généré peut ensuite être brûlé dans la vidéo avec :
    ffmpeg -i clip.mp4 -vf "ass=output.ass" -c:a copy clip_sub.mp4
"""

import json
import sys

# --- Style visuel (ajustable) ---
FONT_NAME = "Montserrat Black"
FONT_SIZE = 22
PRIMARY_COLOR = "&H00FFFFFF"      # blanc (mots pas encore prononcés)
HIGHLIGHT_COLOR = "&H0000D7FF"    # jaune/orange vif (mot en cours) - format BGR
OUTLINE_COLOR = "&H00000000"      # noir
OUTLINE_WIDTH = 3
MAX_WORDS_PER_LINE = 4            # regroupement à l'écran (2-4 = lisible en vertical)


def ts(seconds):
    """Convertit des secondes en timestamp .ass (H:MM:SS.CC)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def collect_words(segments, clip_start, clip_end):
    """Extrait tous les mots (avec timestamps) qui tombent dans la fenêtre du clip."""
    words = []
    for seg in segments:
        for w in seg.get("words", []):
            if clip_start <= w["start"] < clip_end:
                words.append(w)
    return words


def chunk_words(words, size):
    for i in range(0, len(words), size):
        yield words[i:i + size]


def build_ass_header():
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{FONT_SIZE},{PRIMARY_COLOR},{PRIMARY_COLOR},{OUTLINE_COLOR},&H80000000,1,0,0,0,100,100,0,0,1,{OUTLINE_WIDTH},0,2,80,80,220,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_dialogue_lines(word_chunks, clip_start):
    """Une ligne .ass PAR MOT ACTIF : le texte complet du groupe est affiché en
    continu, mais à chaque instant seul le mot en cours porte la couleur
    HIGHLIGHT_COLOR (override \\c), les autres restent en PRIMARY_COLOR.
    C'est plus fiable sur libass/ffmpeg que le karaoke \\k pour un vrai
    changement de couleur mot-par-mot (style Opus/CapCut)."""
    lines = []
    for chunk in word_chunks:
        words_clean = [w["word"].strip().replace("{", "").replace("}", "") for w in chunk]

        for i, w in enumerate(chunk):
            start = max(0, w["start"] - clip_start)
            end = max(0, w["end"] - clip_start)

            parts = []
            for j, word_text in enumerate(words_clean):
                if j == i:
                    parts.append(f"{{\\c{HIGHLIGHT_COLOR}}}{word_text}{{\\c{PRIMARY_COLOR}}}")
                else:
                    parts.append(word_text)
            text = " ".join(parts)

            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}")
    return lines


def generate(transcript_path, clip_start, clip_end, output_path):
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    words = collect_words(transcript["segments"], clip_start, clip_end)
    if not words:
        raise ValueError("Aucun mot trouvé dans cette fenêtre de temps — vérifie les timestamps.")

    word_chunks = list(chunk_words(words, MAX_WORDS_PER_LINE))
    dialogue_lines = build_dialogue_lines(word_chunks, clip_start)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(build_ass_header())
        f.write("\n".join(dialogue_lines))
        f.write("\n")

    print(f"OK -> {output_path} ({len(dialogue_lines)} lignes, {len(words)} mots)")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("Usage: python generate_subtitles.py transcript.json <start> <end> output.ass")
        sys.exit(1)

    generate(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4])

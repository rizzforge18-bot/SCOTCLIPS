"""
generate_subtitles.py

Genere un fichier sous-titres .ass, style moderne "viral" (Insta Reels /
TikTok) : gros texte en majuscules, fond encadre semi-opaque, mot en
cours en couleur vive + leger effet de zoom ("pop"), a partir des
timestamps mots de faster-whisper.

Usage:
    python generate_subtitles.py transcript.json 45.2 78.9 output.ass [width] [height]
    (width/height = resolution de la video finale, defaut 1080x1920 pour du 9:16 ;
     passer 1080 1080 pour une video carree 1:1)

Le fichier .ass genere peut ensuite etre brule dans la video avec :
    ffmpeg -i clip.mp4 -vf "ass=output.ass" -c:a copy clip_sub.mp4
"""

import json
import sys

# --- Style visuel (ajustable) ---
FONT_NAME = "DejaVu Sans"
PRIMARY_COLOR = "&H00FFFFFF"      # blanc (mots pas encore prononces)
HIGHLIGHT_COLOR = "&H0000F2FE"    # jaune/or vif (mot en cours) - format BGR
BOX_COLOR = "&H99000000"          # fond noir semi-opaque derriere le texte
OUTLINE_COLOR = "&H00000000"      # contour noir
OUTLINE_WIDTH = 2
MAX_WORDS_PER_LINE = 3            # petits groupes = plus lisible et plus "punchy"
POP_SCALE = 118                   # % d'agrandissement du mot actif (effet de zoom)


def ts(seconds):
    """Convertit des secondes en timestamp .ass (H:MM:SS.CC)"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def collect_words(segments, clip_start, clip_end):
    """Extrait tous les mots (avec timestamps) qui tombent dans la fenetre du clip."""
    words = []
    for seg in segments:
        for w in seg.get("words", []):
            if clip_start <= w["start"] < clip_end:
                words.append(w)
    return words


def chunk_words(words, size):
    for i in range(0, len(words), size):
        yield words[i:i + size]


def build_ass_header(width, height):
    # Taille de police proportionnelle a la largeur de sortie (~7% de la largeur)
    font_size = max(28, int(width * 0.075))
    margin_v = int(height * 0.12)

    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT_NAME},{font_size},{PRIMARY_COLOR},{PRIMARY_COLOR},{OUTLINE_COLOR},{BOX_COLOR},1,0,0,0,100,100,0,0,3,{OUTLINE_WIDTH},0,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def build_dialogue_lines(word_chunks, clip_start):
    """Une ligne .ass PAR MOT ACTIF : le texte complet du groupe (en MAJUSCULES,
    style viral) est affiche en continu, mais a chaque instant seul le mot en
    cours porte la couleur HIGHLIGHT_COLOR et un leger effet de zoom (\\fscx/\\fscy),
    les autres restent en PRIMARY_COLOR taille normale."""
    lines = []
    for chunk in word_chunks:
        words_clean = [w["word"].strip().upper().replace("{", "").replace("}", "") for w in chunk]

        for i, w in enumerate(chunk):
            start = max(0, w["start"] - clip_start)
            end = max(0, w["end"] - clip_start)

            parts = []
            for j, word_text in enumerate(words_clean):
                if j == i:
                    parts.append(
                        f"{{\\c{HIGHLIGHT_COLOR}\\fscx{POP_SCALE}\\fscy{POP_SCALE}}}{word_text}"
                        f"{{\\c{PRIMARY_COLOR}\\fscx100\\fscy100}}"
                    )
                else:
                    parts.append(word_text)
            text = " ".join(parts)

            lines.append(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}")
    return lines


def generate(transcript_path, clip_start, clip_end, output_path, width=1080, height=1920):
    with open(transcript_path, "r", encoding="utf-8") as f:
        transcript = json.load(f)

    words = collect_words(transcript["segments"], clip_start, clip_end)
    if not words:
        raise ValueError("Aucun mot trouve dans cette fenetre de temps - verifie les timestamps.")

    word_chunks = list(chunk_words(words, MAX_WORDS_PER_LINE))
    dialogue_lines = build_dialogue_lines(word_chunks, clip_start)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(build_ass_header(width, height))
        f.write("\n".join(dialogue_lines))
        f.write("\n")

    print(f"OK -> {output_path} ({len(dialogue_lines)} lignes, {len(words)} mots)")


if __name__ == "__main__":
    if len(sys.argv) not in (5, 7):
        print("Usage: python generate_subtitles.py transcript.json <start> <end> output.ass [width height]")
        sys.exit(1)

    w = int(sys.argv[5]) if len(sys.argv) == 7 else 1080
    h = int(sys.argv[6]) if len(sys.argv) == 7 else 1920
    generate(sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), sys.argv[4], w, h)

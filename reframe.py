"""
reframe.py

Recadre une vidéo (typiquement 16:9) en 1:1 ou 9:16 en suivant
dynamiquement la position du visage détecté, façon Opus/CapCut
"auto-reframe". Détection par OpenCV (Haar Cascade, pas de modèle
à télécharger), lissage de la trajectoire, puis crop dynamique
via ffmpeg (filtre sendcmd + crop).

Usage:
    python reframe.py input.mp4 output.mp4 9:16
    python reframe.py input.mp4 output.mp4 1:1
"""

import subprocess
import sys
import cv2
import numpy as np

SAMPLE_EVERY_N_FRAMES = 5   # fréquence d'échantillonnage pour la détection
SMOOTHING_WINDOW = 9        # lissage de la trajectoire (impair, plus grand = plus stable/moins réactif)
OUTPUT_HEIGHT = 1920        # résolution finale (portrait) ; 1:1 sera recadré au carré à partir de là

FACE_CASCADE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")


def get_video_info(path):
    cap = cv2.VideoCapture(path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()
    return w, h, fps, frame_count


def detect_face_centers(path, frame_w, frame_h, fps, frame_count):
    """Retourne une liste de (temps_s, centre_x_normalise) échantillonnée."""
    cap = cv2.VideoCapture(path)
    samples = []
    idx = 0
    last_cx = 0.5  # centre de l'image par défaut si aucun visage détecté

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if idx % SAMPLE_EVERY_N_FRAMES == 0:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = FACE_CASCADE.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(40, 40))

            if len(faces) > 0:
                # Priorité au plus grand visage détecté (probablement celui qui parle / au premier plan)
                x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
                cx = (x + w / 2) / frame_w
                last_cx = cx
            else:
                cx = last_cx

            t = idx / fps
            samples.append((t, cx))

        idx += 1

    cap.release()
    return samples


def smooth(values, window):
    if len(values) < window:
        return values
    kernel = np.ones(window) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")


def build_sendcmd_file(samples, frame_w, crop_w, out_path):
    """Génère le fichier de commandes ffmpeg pour faire varier x du crop dans le temps."""
    if not samples:
        return None

    times = [s[0] for s in samples]
    cx_norm = smooth([s[1] for s in samples], SMOOTHING_WINDOW)

    lines = []
    for t, cx in zip(times, cx_norm):
        center_px = cx * frame_w
        x = center_px - crop_w / 2
        x = max(0, min(frame_w - crop_w, x))
        lines.append(f"{t:.2f} crop@c x '{int(x)}';")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return out_path


STANDARD_SIZES = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
}


def reframe(input_path, output_path, aspect="9:16"):
    frame_w, frame_h, fps, frame_count = get_video_info(input_path)

    ratio_w, ratio_h = (int(x) for x in aspect.split(":"))
    crop_h = frame_h
    crop_w = int(crop_h * ratio_w / ratio_h)
    if crop_w > frame_w:
        # La vidéo source n'est pas assez large pour ce ratio à pleine hauteur :
        # on recadre plutôt sur la hauteur.
        crop_w = frame_w
        crop_h = int(crop_w * ratio_h / ratio_w)

    samples = detect_face_centers(input_path, frame_w, frame_h, fps, frame_count)
    cmd_file = output_path + ".cmds.txt"
    build_sendcmd_file(samples, frame_w, crop_w, cmd_file)

    out_w, out_h = STANDARD_SIZES.get(aspect, (crop_w, crop_h))

    y_offset = max(0, (frame_h - crop_h) // 2)

    vf = (
        f"sendcmd=f='{cmd_file}',"
        f"crop@c=w={crop_w}:h={crop_h}:x={(frame_w - crop_w) // 2}:y={y_offset},"
        f"scale={out_w}:{out_h}"
    )

    subprocess.run(
        ["ffmpeg", "-y", "-i", input_path, "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-c:a", "aac", output_path],
        check=True,
        capture_output=True,
        text=True,
    )

    return output_path, out_w, out_h


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python reframe.py input.mp4 output.mp4 <1:1|9:16>")
        sys.exit(1)

    path, w, h = reframe(sys.argv[1], sys.argv[2], sys.argv[3])
    print(f"OK -> {path} ({w}x{h})")

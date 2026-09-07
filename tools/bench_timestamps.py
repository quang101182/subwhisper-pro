#!/usr/bin/env python3
"""Banc TIMESTAMPS SubWhisper — la précision du calage, pas celle du texte.

POURQUOI CE BANC EXISTE
-----------------------
Le banc `bench_stt_multilingue.py` mesure ce que le moteur ENTEND. Il ne dit rien
de ce qui décide de la qualité d'un sous-titre : le CALAGE. Un texte parfait posé
300 ms trop tôt est inutilisable ; un texte moyen bien calé se lit très bien.

LA VÉRITÉ TERRAIN, ET COMMENT ELLE EST FABRIQUÉE
------------------------------------------------
On ne peut pas connaître les vraies frontières de mots d'un audio quelconque. Alors
on les FABRIQUE : on concatène N phrases FLEURS séparées par un silence de durée
connue. Les frontières deviennent exactes par construction — on sait à la
milliseconde près où chaque phrase commence.

⚠️ Ce que ça mesure et ce que ça ne mesure pas : un silence net entre phrases est
un cas FACILE. Un moteur qui échoue ici échouera sur de la parole continue ; mais
réussir ici ne prouve pas qu'il réussira sur un dialogue qui se chevauche. C'est
un plancher de qualité, pas un certificat.

CE QUI EST COMPARÉ
------------------
  Groq   : `verbose_json` + `timestamp_granularities[]=segment` -> des SEGMENTS.
           C'est ce que SubWhisper utilise aujourd'hui (`app.html:2803-2804`).
  Gemini : `mode={"type":"verbatim","timestamp_granularities":["word"]}` -> des MOTS
           (`annotations[].type == "word_info"`, offsets en "2.200s").
           ⚠️ `segment` ne rend AUCUN timestamp chez Gemini (mesuré) : c'est mot ou rien.
           ⚠️ Et `custom_vocabulary` est INCOMPATIBLE avec les timestamps (doc Google) :
              on ne peut pas avoir à la fois les noms propres et le calage.

USAGE : python bench_timestamps.py [--phrases 6] [--silence 0.8] [--lang fr_fr]
Sortie : results_timestamps.json + summary_timestamps.md
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np
import requests

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bench_stt_multilingue import (  # noqa: E402
    AUTH, GATEWAY, BCP47, LANGS, load_samples, wav_bytes,
)


def debut_parole(arr: np.ndarray, sr: int, seuil_rel: float = 0.02,
                 fenetre_ms: int = 20) -> float:
    """Instant où la parole commence VRAIMENT dans le clip.

    ⛔ Le piège qui a invalidé la 1re version de ce banc (07/09/2026) : les clips
    FLEURS commencent par ~2 s de SILENCE. Prendre le début du clip comme frontière
    revenait à mesurer ce silence, pas le calage du moteur — les deux moteurs
    ressortaient à 0,8-1,2 s d'écart, ce qui ne voulait rien dire. La vérité terrain
    d'un timestamp de parole, c'est le début de la PAROLE.
    """
    n = max(1, int(sr * fenetre_ms / 1000))
    a = np.abs(arr.astype(np.float32))
    if a.max() <= 0:
        return 0.0
    # RMS glissant grossier (moyenne par blocs) : suffisant et rapide.
    nb = len(a) // n
    if nb == 0:
        return 0.0
    blocs = a[:nb * n].reshape(nb, n).mean(axis=1)
    seuil = seuil_rel * blocs.max()
    idx = np.argmax(blocs >= seuil)
    return float(idx * n / sr)


def build_audio(samples: list[dict], silence_s: float) -> tuple[bytes, list[float], int]:
    """Concatène les phrases avec un silence connu.

    Rend (wav, débuts de PAROLE absolus, sr) — pas les débuts de clip (cf.
    `debut_parole`).
    """
    sr = samples[0]["sr"]
    sil = np.zeros(int(silence_s * sr), dtype=np.float32)
    pieces, starts, t = [], [], 0.0
    for i, s in enumerate(samples):
        if s["sr"] != sr:
            raise SystemExit("sample rates hétérogènes — banc invalide")
        if i:
            pieces.append(sil)
            t += silence_s
        starts.append(t + debut_parole(s["arr"], sr))
        pieces.append(s["arr"].astype(np.float32))
        t += len(s["arr"]) / sr
    return wav_bytes(np.concatenate(pieces), sr), starts, sr


def groq_segments(audio: bytes, lang: str):
    t0 = time.time()
    r = requests.post(
        GATEWAY + "/api/groq",
        headers={**AUTH, "X-Api-Path": "/openai/v1/audio/transcriptions"},
        files={"file": ("a.wav", audio, "audio/wav")},
        data={"model": "whisper-large-v3-turbo", "language": lang,
              "response_format": "verbose_json",
              "timestamp_granularities[]": "segment"},
        timeout=300)
    lat = time.time() - t0
    if r.status_code != 200:
        return None, lat, f"HTTP {r.status_code}: {r.text[:180]}"
    segs = r.json().get("segments") or []
    return [(float(s["start"]), float(s["end"]), s.get("text", "").strip())
            for s in segs], lat, None


_OFF_RE = re.compile(r"^([\d.]+)s?$")


def _sec(v) -> float | None:
    if v is None:
        return None
    m = _OFF_RE.match(str(v).strip())
    return float(m.group(1)) if m else None


def gemini_words(audio: bytes, lang: str):
    t0 = time.time()
    body = {"model": "gemini-3.5-transcribe",
            "input": [{"type": "audio", "mime_type": "audio/wav",
                       "data": base64.b64encode(audio).decode("ascii")}],
            "generation_config": {"transcription_config": {
                "language_codes": [BCP47.get(lang, lang)],
                "mode": {"type": "verbatim",
                         "timestamp_granularities": ["word"]}}}}
    r = requests.post(GATEWAY + "/api/gemini/v1beta/interactions",
                      headers={**AUTH, "Content-Type": "application/json"},
                      data=json.dumps(body), timeout=600)
    lat = time.time() - t0
    if r.status_code != 200:
        return None, lat, f"HTTP {r.status_code}: {r.text[:180]}"
    words = []
    for st in r.json().get("steps", []):
        for c in st.get("content", []):
            for an in c.get("annotations", []) or []:
                if an.get("type") != "word_info":
                    continue
                s0, s1 = _sec(an.get("start_offset")), _sec(an.get("end_offset"))
                if s0 is not None:
                    words.append((s0, s1, an.get("text", "")))
    return words, lat, None


def ecarts(bornes: list[float], debuts: list[float]) -> list[float]:
    """Pour chaque frontière connue, l'écart au début d'unité le plus proche."""
    return [min(abs(d - b) for d in debuts) for b in bornes] if debuts else []


def stats(xs: list[float]) -> dict:
    if not xs:
        return {"n": 0}
    ys = sorted(xs)
    n = len(ys)
    return {"n": n,
            "moyenne_ms": round(sum(ys) / n * 1000),
            "mediane_ms": round((ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2) * 1000),
            "pire_ms": round(ys[-1] * 1000),
            "sous_200ms": sum(1 for v in ys if v <= 0.200),
            "sous_500ms": sum(1 for v in ys if v <= 0.500)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phrases", type=int, default=6)
    ap.add_argument("--silence", type=float, default=0.8)
    ap.add_argument("--lang", type=str, default="fr_fr")
    args = ap.parse_args()

    label, hint = LANGS[args.lang]
    samples = load_samples(args.lang, args.phrases)
    if len(samples) < 2:
        print("pas assez de samples", flush=True)
        return 1
    audio, starts, sr = build_audio(samples, args.silence)
    total = len(audio) / (sr * 2)
    print(f"{label} : {len(samples)} phrases concatenees, {total:.1f}s, "
          f"silence {args.silence}s", flush=True)
    print("debuts de PAROLE (s, silence de tete des clips retire) :", [round(t, 2) for t in starts], flush=True)

    res = {"timestamp": datetime.now().isoformat(timespec="seconds"),
           "langue": args.lang, "phrases": len(samples), "silence_s": args.silence,
           "duree_s": round(total, 2), "bornes": [round(t, 3) for t in starts],
           "moteurs": {}}

    segs, lat_g, err_g = groq_segments(audio, hint)
    time.sleep(3.2)
    words, lat_e, err_e = gemini_words(audio, hint)

    if err_g:
        print("Groq ERREUR:", err_g, flush=True)
    else:
        e = ecarts(starts, [s[0] for s in segs])
        res["moteurs"]["groq_whisper_turbo"] = {
            "unite": "segment", "n_unites": len(segs), "latence_s": round(lat_g, 2),
            "ecarts_s": [round(v, 3) for v in e], **stats(e)}
        print(f"\nGroq : {len(segs)} segments en {lat_g:.2f}s -> {stats(e)}", flush=True)

    if err_e:
        print("Gemini ERREUR:", err_e, flush=True)
    else:
        e = ecarts(starts, [w[0] for w in words])
        res["moteurs"]["gemini_35_transcribe"] = {
            "unite": "mot", "n_unites": len(words), "latence_s": round(lat_e, 2),
            "ecarts_s": [round(v, 3) for v in e], **stats(e)}
        print(f"Gemini : {len(words)} mots en {lat_e:.2f}s -> {stats(e)}", flush=True)

    (HERE / "results_timestamps.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

    L = [f"# Banc timestamps SubWhisper — {res['timestamp'][:10]}", "",
         f"{len(samples)} phrases {label} concatenees ({total:.1f}s), separees par "
         f"{args.silence}s de silence. Les frontieres sont donc EXACTES par construction.",
         "", "Ecart = distance entre chaque frontiere connue et le debut d'unite le plus "
         "proche rendu par le moteur.", "",
         "| Moteur | Unite | Nb | Ecart moyen | Median | Pire | <=200ms | <=500ms | Latence |",
         "|---|---|---|---|---|---|---|---|---|"]
    for key, m in res["moteurs"].items():
        L.append(f"| `{key}` | {m['unite']} | {m['n_unites']} | {m['moyenne_ms']} ms | "
                 f"{m['mediane_ms']} ms | {m['pire_ms']} ms | "
                 f"{m['sous_200ms']}/{m['n']} | {m['sous_500ms']}/{m['n']} | "
                 f"{m['latence_s']}s |")
    L += ["", "⚠️ Un silence net entre phrases est un cas FACILE : ce banc mesure un "
          "plancher de qualite, pas le comportement sur parole continue ou dialogue "
          "qui se chevauche.", "",
          "⚠️ Chez Gemini, `timestamp_granularities:[\"segment\"]` ne rend AUCUN "
          "timestamp (mesure du 07/09) : c'est le MOT ou rien. Et `custom_vocabulary` "
          "est incompatible avec les timestamps — il faut choisir entre le calage et "
          "les noms propres."]
    (HERE / "summary_timestamps.md").write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())

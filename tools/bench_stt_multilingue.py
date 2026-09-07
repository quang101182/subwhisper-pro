#!/usr/bin/env python3
"""Banc STT multilingue SubWhisper — Groq Whisper Turbo vs Gemini 3.5 Transcribe.

LA QUESTION
-----------
SubWhisper tourne aujourd'hui sur `whisper-large-v3-turbo` chez Groq, et c'est le
SEUL chemin réellement atteignable (les branches OpenAI et AssemblyAI existent mais
tous les getters de clés renvoient `''` en dur — `app.html:1989-2009`). Google a
sorti le 26/08/2026 `gemini-3.5-transcribe`, un modèle STT dédié. Le verdict
DictoKey du 07/09 l'a écarté pour la dictée (péage fixe de ~2,8 s) mais l'a désigné
comme le meilleur candidat pour SubWhisper, où l'audio est long et le péage amorti.

Il ne s'agit PAS de remplacer Groq : l'objectif est de savoir sur QUELLES LANGUES
un second moteur, proposé au choix, apporterait quelque chose.

LANGUES (celles de l'usage réel de Quang, pas un panel académique)
------------------------------------------------------------------
  fr_fr        français
  en_us        anglais
  de_de        allemand
  cmn_hans_cn  chinois mandarin simplifié
  ja_jp        japonais
  ko_kr        coréen

⚠️ LE PIÈGE DE MESURE, ET IL EST STRUCTUREL : le WER (word error rate) compte des
MOTS séparés par des espaces. Le chinois et le japonais n'en écrivent pas, et le
coréen agglutine. Un WER sur ces langues ne mesure pas la reconnaissance, il mesure
la segmentation — deux transcriptions correctes mais découpées différemment
donneraient 100 % d'erreur. ⇒ pour zh/ja/ko le verdict se lit sur le **CER**
(character error rate), et le WER y est affiché grisé, pour mémoire seulement.

USAGE
-----
  python bench_stt_multilingue.py --smoke              # 2 samples FR, valide la mécanique
  python bench_stt_multilingue.py                      # 10 samples x 6 langues
  python bench_stt_multilingue.py --langs ja_jp,ko_kr --samples 15

Sortie : results_multilingue.json + summary_multilingue.md
"""
from __future__ import annotations

import argparse
import base64
import io
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

import jiwer
import requests
import soundfile as sf

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
GATEWAY = "https://api-gateway.quang101182.workers.dev"

# Le secret ne vit dans AUCUN code : model_watch.worker_secret() le lit dans
# l'environnement ou llm-cli/.env.
sys.path.insert(0, str(REPO / "llm-cli"))
from model_watch import worker_secret  # noqa: E402

AUTH = {"Authorization": f"Bearer {worker_secret()}"}

# Corpus partagé avec le banc DictoKey (424-692 Mo par langue, gitignoré des deux
# côtés). Le streaming HuggingFace ne rend plus un seul sample : le parquet publié
# n'a qu'UN row group, donc lire la 1re ligne = tout télécharger.
FLEURS_DIR = REPO / "dictokey" / "tools" / "fleurs"
FLEURS_URL = "https://huggingface.co/api/datasets/google/fleurs/parquet/{lang}/test/0.parquet"

DELAY_S = 3.2  # le gateway plafonne à 20 req/min (fenêtre FIXE) — viser 18

# Les langues où le WER n'a pas de sens : pas d'espaces (zh/ja) ou agglutination
# (ko). Le verdict s'y lit sur le CER.
CER_LANGS = {"cmn_hans_cn", "ja_jp", "ko_kr"}

LANGS = {
    "fr_fr":       ("Francais",  "fr"),
    "en_us":       ("Anglais",   "en"),
    "de_de":       ("Allemand",  "de"),
    "cmn_hans_cn": ("Chinois",   "zh"),
    "ja_jp":       ("Japonais",  "ja"),
    "ko_kr":       ("Coreen",    "ko"),
}

# BCP-47 attendu par Gemini (transcription_config.language_codes).
BCP47 = {"fr": "fr-FR", "en": "en-US", "de": "de-DE",
         "zh": "cmn-Hans-CN", "ja": "ja-JP", "ko": "ko-KR"}

MODELS = {
    "groq_whisper_turbo": {
        "kind": "groq",
        "model": "whisper-large-v3-turbo",
        "usd_per_hour": 0.04,
        "role": "BASELINE — le seul moteur réellement atteignable dans SubWhisper",
    },
    "gemini_35_transcribe": {
        "kind": "gemini",
        "model": "gemini-3.5-transcribe",
        "usd_per_hour": 0.005 * 60,   # $0,005/min annoncé
        "role": "challenger — modèle STT dédié Google, sorti le 26/08/2026",
    },
}


# ── normalisation ────────────────────────────────────────────────────────────
_PUNCT_RE = re.compile(r"[^\w\s']", re.UNICODE)
# Ponctuation pleine largeur CJK : absente de \w, mais aussi de la plage ASCII
# que _PUNCT_RE couvre déjà. On la retire explicitement pour ne pas compter une
# virgule idéographique comme une erreur de caractère.
_CJK_PUNCT = "、。「」『』・〜！？：；，．（）【】〈〉《》"


def normalize(t: str, cjk: bool = False) -> str:
    t = _PUNCT_RE.sub(" ", t.lower())
    if cjk:
        for ch in _CJK_PUNCT:
            t = t.replace(ch, " ")
        # Sans espaces lexicaux, le CER doit comparer des caractères nus :
        # une différence d'espacement n'est pas une erreur de reconnaissance.
        return "".join(t.split())
    return " ".join(t.split())


def metrics(ref: str, hyp: str | None, cjk: bool) -> dict:
    out = {"wer": None, "cer": None, "nwer": None, "ncer": None}
    if not hyp:
        return out
    nref, nhyp = normalize(ref, cjk), normalize(hyp, cjk)
    pairs = [("wer", jiwer.wer, ref, hyp), ("cer", jiwer.cer, ref, hyp),
             ("ncer", jiwer.cer, nref, nhyp)]
    # Le WER normalisé n'a de sens que si les mots existent.
    if not cjk:
        pairs.append(("nwer", jiwer.wer, nref, nhyp))
    for nom, fn, r, h in pairs:
        try:
            out[nom] = fn(r.strip(), h.strip())
        except Exception:
            out[nom] = None
    return out


# ── moteurs ──────────────────────────────────────────────────────────────────
def wav_bytes(arr, sr: int) -> bytes:
    buf = io.BytesIO()
    sf.write(buf, arr, sr, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()


def transcribe_groq(audio: bytes, lang: str) -> tuple[str | None, float, str | None]:
    t0 = time.time()
    try:
        r = requests.post(
            GATEWAY + "/api/groq",
            headers={**AUTH, "X-Api-Path": "/openai/v1/audio/transcriptions"},
            files={"file": ("audio.wav", audio, "audio/wav")},
            data={"model": MODELS["groq_whisper_turbo"]["model"],
                  "language": lang, "response_format": "json"},
            timeout=180,
        )
        lat = time.time() - t0
        if r.status_code != 200:
            return None, lat, f"HTTP {r.status_code}: {r.text[:180]}"
        return (r.json().get("text") or "").strip(), lat, None
    except Exception as e:
        return None, time.time() - t0, f"{type(e).__name__}: {e}"


def transcribe_gemini(audio: bytes, lang: str) -> tuple[str | None, float, str | None]:
    """Interactions API — c'est la seule qui accepte transcription_config.

    Vérifié en direct le 07/09/2026 : l'audio se passe en `data`/`mime_type` A PLAT
    (`inline_data` -> 400 ici), et la réponse se lit dans steps[].content[].text.
    """
    t0 = time.time()
    body = {"model": MODELS["gemini_35_transcribe"]["model"],
            "input": [{"type": "audio", "mime_type": "audio/wav",
                       "data": base64.b64encode(audio).decode("ascii")}],
            "generation_config": {"transcription_config": {
                "language_codes": [BCP47.get(lang, lang)]}}}
    try:
        r = requests.post(
            GATEWAY + "/api/gemini/v1beta/interactions",
            headers={**AUTH, "Content-Type": "application/json"},
            data=json.dumps(body), timeout=300,
        )
        lat = time.time() - t0
        if r.status_code != 200:
            return None, lat, f"HTTP {r.status_code}: {r.text[:180]}"
        j = r.json()
        txt = "".join(c.get("text", "") for st in j.get("steps", [])
                      for c in st.get("content", []))
        return txt.strip(), lat, None
    except Exception as e:
        return None, time.time() - t0, f"{type(e).__name__}: {e}"


RUNNERS = {"groq": transcribe_groq, "gemini": transcribe_gemini}


# ── corpus ───────────────────────────────────────────────────────────────────
def fleurs_parquet(lang_code: str) -> Path | None:
    FLEURS_DIR.mkdir(parents=True, exist_ok=True)
    dest = FLEURS_DIR / f"{lang_code}_test.parquet"
    if dest.exists() and dest.stat().st_size > 1_000_000:
        return dest
    url = FLEURS_URL.format(lang=lang_code)
    print(f"  telechargement {lang_code} (~400-700 Mo)...", flush=True)
    tmp = dest.with_suffix(".part")
    try:
        with requests.get(url, stream=True, timeout=900) as r:
            r.raise_for_status()
            with open(tmp, "wb") as f:
                for chunk in r.iter_content(1 << 20):
                    f.write(chunk)
        tmp.replace(dest)
        print(f"  -> {dest.stat().st_size >> 20} Mo", flush=True)
        return dest
    except Exception as e:
        print(f"  ECHEC {lang_code}: {e}", flush=True)
        tmp.unlink(missing_ok=True)
        return None


def load_samples(lang_code: str, n: int) -> list[dict]:
    import pyarrow.parquet as pq
    path = fleurs_parquet(lang_code)
    if path is None:
        return []
    tb = pq.ParquetFile(path).read_row_group(0, columns=["audio", "transcription"])
    out = []
    for row in tb.to_pylist():
        if len(out) >= n:
            break
        raw = row["audio"]
        if isinstance(raw, dict):
            raw = raw.get("bytes")
        if not raw:
            continue
        try:
            arr, sr = sf.read(io.BytesIO(raw), dtype="float32")
        except Exception:
            continue
        if arr.ndim > 1:
            arr = arr.mean(axis=1)
        ref = (row.get("transcription") or "").strip()
        if not ref:
            continue
        out.append({"ref": ref, "arr": arr, "sr": sr, "dur": len(arr) / sr})
    return out


# ── main ─────────────────────────────────────────────────────────────────────
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--langs", type=str, default=None)
    ap.add_argument("--models", type=str, default=None)
    args = ap.parse_args()

    if args.smoke:
        langs, n = {"fr_fr": LANGS["fr_fr"]}, 2
    else:
        langs = ({c: LANGS[c] for c in args.langs.split(",") if c in LANGS}
                 if args.langs else LANGS)
        n = args.samples
    models = ({k: MODELS[k] for k in args.models.split(",") if k in MODELS}
              if args.models else MODELS)

    res_path = HERE / "results_multilingue.json"
    res = {"timestamp": datetime.now().isoformat(timespec="seconds"),
           "samples_par_langue": n, "by_lang": {}}
    # Un run partiel ENRICHIT le fichier existant au lieu de l'ecraser.
    if res_path.exists() and (args.langs or args.models) and not args.smoke:
        try:
            res["by_lang"] = json.loads(res_path.read_text(encoding="utf-8")).get("by_lang", {})
        except Exception:
            pass

    for code, (label, hint) in langs.items():
        cjk = code in CER_LANGS
        print(f"\n=== {label} ({code}) — verdict sur {'CER' if cjk else 'WER'} ===", flush=True)
        samples = load_samples(code, n)
        if not samples:
            print("  aucun sample -> langue ignoree", flush=True)
            continue
        print(f"  {len(samples)} samples", flush=True)

        acc = {k: {"wer": [], "cer": [], "nwer": [], "ncer": [], "lat": [],
                   "dur": [], "err": []} for k in models}

        for i, s in enumerate(samples, 1):
            audio = wav_bytes(s["arr"], s["sr"])
            print(f"  [{i}/{len(samples)}] {s['dur']:.1f}s | {s['ref'][:48]!r}", flush=True)
            for key, cfg in models.items():
                txt, lat, err = RUNNERS[cfg["kind"]](audio, hint)
                m = metrics(s["ref"], txt, cjk)
                a = acc[key]
                a["lat"].append(lat)
                a["dur"].append(s["dur"])
                if err:
                    a["err"].append(err)
                else:
                    for nom in ("wer", "cer", "nwer", "ncer"):
                        if m[nom] is not None:
                            a[nom].append(m[nom])
                cle = "ncer" if cjk else "nwer"
                v = f"{m[cle]:.1%}" if m[cle] is not None else "n/a"
                print(f"      {'OK ' if not err else 'ERR'} {key:22s} "
                      f"{cle}={v:>7s} {lat:5.2f}s{(' | ' + err[:60]) if err else ''}",
                      flush=True)
                time.sleep(DELAY_S)

        moy = lambda xs: (sum(xs) / len(xs)) if xs else None

        def med(xs):
            """La MEDIANE, et elle n'est pas un raffinement statistique ici.

            Mesure du 07/09 : sur 10 phrases chinoises, Gemini bat Groq 8 fois,
            puis hallucine un nom propre etranger sur la 9e (CER 140 % : il
            INVENTE du texte absent de l'audio). La moyenne passe alors de ~2 %
            a 16 % et inverse le classement. La moyenne decrit le pire cas, la
            mediane le cas courant : les DEUX sont necessaires pour decider,
            aucune ne suffit seule.
            """
            if not xs:
                return None
            ys = sorted(xs)
            n = len(ys)
            return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2

        agg = {}
        for key, a in acc.items():
            scores = a["ncer"] if cjk else a["nwer"]
            # Au-dela de 100 %, l'hypothese est plus longue que la reference :
            # le modele a AJOUTE du texte. Pour du sous-titre c'est pire qu'une
            # erreur de caractere, ca se compte a part.
            agg[key] = {
                "n_ok": len(a["ncer"]), "n_err": len(a["err"]),
                "nwer": moy(a["nwer"]), "ncer": moy(a["ncer"]),
                "median": med(scores),
                "n_hallucination": sum(1 for v in scores if v > 1.0),
                "pire": max(scores) if scores else None,
                "latence_s": moy(a["lat"]), "duree_moy_s": moy(a["dur"]),
                "ratio_temps_reel": (moy(a["lat"]) / moy(a["dur"])) if a["lat"] and a["dur"] else None,
                "usd_par_heure": MODELS[key]["usd_per_hour"],
                "erreurs": a["err"][:2],
            }
        prev = res["by_lang"].get(code, {}).get("agg", {})
        prev.update(agg)
        res["by_lang"][code] = {"label": label, "metrique": "CER" if cjk else "WER",
                                "agg": prev}

    res_path.write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str),
                        encoding="utf-8")

    # ── verdict lisible
    L = [f"# Banc STT multilingue SubWhisper — {res['timestamp'][:10]}", "",
         f"{n} samples/langue, dataset FLEURS (Google, open). Metriques NORMALISEES "
         "(casse + ponctuation retirees).", "",
         "⚠️ **Le chinois, le japonais et le coreen se lisent sur le CER**, pas le WER : "
         "ces langues n'ecrivent pas d'espaces entre les mots, un WER y mesurerait la "
         "segmentation et non la reconnaissance.", "",
         "⚠️ **Lire la MEDIANE autant que la moyenne.** Une seule phrase ou le modele "
         "hallucine (score > 100 % = il a AJOUTE du texte) suffit a doubler une moyenne "
         "et a inverser un classement. La colonne `halluc.` compte ces cas.", "",
         "| Langue | Metrique | Modele | Moyenne | Mediane | halluc. | pire | Latence | $/h |",
         "|---|---|---|---|---|---|---|---|---|"]
    for code, d in res["by_lang"].items():
        met = d["metrique"]
        for key, a in d["agg"].items():
            val = a["ncer"] if met == "CER" else a["nwer"]
            f = lambda v, s="": (format(v, s) if v is not None else "n/a")
            L.append(f"| {d['label']} | {met} | `{MODELS[key]['model']}` | "
                     f"{f(val, '.1%')} | {f(a.get('median'), '.1%')} | "
                     f"{a.get('n_hallucination', 0)} | {f(a.get('pire'), '.0%')} | "
                     f"{f(a['latence_s'], '.2f')}s | ${a['usd_par_heure']:.2f} |")

    L += ["", "## Verdict par langue", ""]
    for code, d in res["by_lang"].items():
        met = d["metrique"]
        base = d["agg"].get("groq_whisper_turbo")
        L.append(f"### {d['label']} (sur {met})")
        if not base or (base["ncer"] if met == "CER" else base["nwer"]) is None:
            L.append("- baseline Groq indisponible : rien de comparable.")
            L.append("")
            continue
        bval = base["ncer"] if met == "CER" else base["nwer"]
        for key, a in d["agg"].items():
            if key == "groq_whisper_turbo":
                continue
            val = a["ncer"] if met == "CER" else a["nwer"]
            if val is None:
                L.append(f"- `{MODELS[key]['model']}` : aucune mesure ({a['n_err']} erreurs)")
                continue
            delta = (val - bval) * 100
            sens = "MIEUX" if delta < 0 else "PIRE"
            rel = (bval - val) / bval * 100 if bval else float("nan")
            dlat = a["latence_s"] / base["latence_s"] if base["latence_s"] else float("nan")
            L.append(f"- `{MODELS[key]['model']}` : {met} moyen {delta:+.1f} pt ({sens}, "
                     f"{rel:+.0f} % relatif), latence x{dlat:.1f}, "
                     f"cout x{a['usd_par_heure'] / base['usd_par_heure']:.1f}")
            bm, am = base.get("median"), a.get("median")
            if bm is not None and am is not None:
                dm = (am - bm) * 100
                L.append(f"  - sur la MEDIANE : {dm:+.1f} pt "
                         f"({'MIEUX' if dm < 0 else 'PIRE'}) — "
                         f"{a.get('n_hallucination', 0)} hallucination(s) contre "
                         f"{base.get('n_hallucination', 0)} pour la baseline")
        L.append("")

    (HERE / "summary_multilingue.md").write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    print(f"\n-> {HERE / 'summary_multilingue.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

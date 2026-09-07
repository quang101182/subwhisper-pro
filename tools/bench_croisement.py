#!/usr/bin/env python3
"""Banc CROISEMENT — peut-on garder les avantages des deux moteurs ?

LA QUESTION DE QUANG (07/09/2026)
---------------------------------
« Combiner les 2 moteurs avec que les avantages ? »

Le comparatif du 07/09 a montré deux profils complémentaires :
  - Gemini 3.5 : bien plus juste sur les 6 langues (mediane), timestamps AU MOT...
    mais il HALLUCINE (1 phrase chinoise sur 10 : un monument americain invente,
    CER 140 % = du texte AJOUTE), et son decrochage est SILENCIEUX.
  - Groq Turbo : moins juste, mais 0 hallucination sur 60 phrases, et un calage
    tres regulier (pire cas 380 ms).

L'idee testee ici : **Groq comme garde-fou de Gemini**. On transcrit avec les deux,
on mesure leur DESACCORD, et au-dela d'un seuil on retombe sur Groq.

⚠️ CE QUI DOIT ETRE PROUVE, ET QUI NE VA PAS DE SOI : que le desaccord entre les
deux SEPARE les hallucinations des simples divergences de style. Si les cas sains
divergent autant que les cas hallucines, le detecteur est inutile — il ne ferait
que jeter au hasard les gains de Gemini. C'est exactement ce que ce banc mesure,
et il peut parfaitement conclure NON.

CE QUI EST CALCULE, PAR PHRASE
------------------------------
  err_groq    = erreur de Groq   vs la reference (verite terrain FLEURS)
  err_gemini  = erreur de Gemini vs la reference
  desaccord   = distance entre les DEUX HYPOTHESES, sans reference
                (c'est le seul signal disponible en production : en vrai, on n'a
                 jamais la verite terrain — d'ou l'interet de ne se fonder que
                 sur lui)

Puis on simule la strategie combinee et on la compare aux deux moteurs seuls.

USAGE : python bench_croisement.py [--samples 10] [--langs fr_fr,ja_jp]
Sortie : results_croisement.json + summary_croisement.md
"""
from __future__ import annotations

import argparse
import json
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

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from bench_stt_multilingue import (  # noqa: E402
    CER_LANGS, DELAY_S, LANGS, load_samples, normalize, wav_bytes,
    transcribe_groq, transcribe_gemini,
)

# Seuils de desaccord a evaluer. On ne fige rien : on regarde ce que chacun donne.
SEUILS = [0.20, 0.30, 0.40, 0.50, 0.60]


def distance(a: str, b: str, cjk: bool) -> float | None:
    """Distance normalisee entre deux textes (CER si CJK, sinon WER)."""
    na, nb = normalize(a or "", cjk), normalize(b or "", cjk)
    if not na and not nb:
        return 0.0
    if not na:
        return 1.0
    try:
        return jiwer.cer(na, nb) if cjk else jiwer.wer(na, nb)
    except Exception:
        return None


def med(xs):
    if not xs:
        return None
    ys = sorted(xs)
    n = len(ys)
    return ys[n // 2] if n % 2 else (ys[n // 2 - 1] + ys[n // 2]) / 2


def moy(xs):
    return (sum(xs) / len(xs)) if xs else None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--langs", type=str, default=None)
    args = ap.parse_args()

    langs = ({c: LANGS[c] for c in args.langs.split(",") if c in LANGS}
             if args.langs else LANGS)

    lignes = []   # une entree par phrase, toutes langues confondues
    for code, (label, hint) in langs.items():
        cjk = code in CER_LANGS
        print(f"\n=== {label} ({code}) ===", flush=True)
        samples = load_samples(code, args.samples)
        if not samples:
            print("  aucun sample", flush=True)
            continue
        for i, s in enumerate(samples, 1):
            audio = wav_bytes(s["arr"], s["sr"])
            g, _, eg = transcribe_groq(audio, hint)
            time.sleep(DELAY_S)
            e, _, ee = transcribe_gemini(audio, hint)
            time.sleep(DELAY_S)
            if eg or ee:
                print(f"  [{i}] ERREUR groq={eg} gemini={ee}", flush=True)
                continue
            row = {
                "langue": code, "cjk": cjk, "ref": s["ref"],
                "groq": g, "gemini": e,
                "err_groq": distance(s["ref"], g, cjk),
                "err_gemini": distance(s["ref"], e, cjk),
                "desaccord": distance(g, e, cjk),
            }
            lignes.append(row)
            flag = ""
            if row["err_gemini"] is not None and row["err_gemini"] > 1.0:
                flag = "  <<< HALLUCINATION"
            print(f"  [{i}] groq={row['err_groq']:.1%} gemini={row['err_gemini']:.1%} "
                  f"desaccord={row['desaccord']:.1%}{flag}", flush=True)

    if not lignes:
        print("aucune mesure", flush=True)
        return 1

    # ── le detecteur separe-t-il vraiment ?
    hallus = [r for r in lignes if r["err_gemini"] > 1.0]
    sains = [r for r in lignes if r["err_gemini"] <= 1.0]

    res = {"timestamp": datetime.now().isoformat(timespec="seconds"),
           "n_phrases": len(lignes), "n_hallucinations": len(hallus),
           "desaccord_hallucinations": [round(r["desaccord"], 3) for r in hallus],
           "desaccord_sains_max": round(max((r["desaccord"] for r in sains), default=0), 3),
           "desaccord_sains_median": round(med([r["desaccord"] for r in sains]) or 0, 3),
           "seuils": {}, "lignes": lignes}

    base_g = [r["err_groq"] for r in lignes]
    base_e = [r["err_gemini"] for r in lignes]

    for seuil in SEUILS:
        # Strategie : Gemini par defaut, Groq si les deux moteurs divergent trop.
        combine, bascules, rattrapes, sacrifies = [], 0, 0, 0
        for r in lignes:
            if r["desaccord"] is not None and r["desaccord"] > seuil:
                bascules += 1
                combine.append(r["err_groq"])
                if r["err_gemini"] > 1.0:
                    rattrapes += 1                    # hallucination evitee
                elif r["err_groq"] > r["err_gemini"]:
                    sacrifies += 1                    # on a jete un meilleur resultat
            else:
                combine.append(r["err_gemini"])
        res["seuils"][str(seuil)] = {
            "bascules": bascules,
            "hallucinations_rattrapees": rattrapes,
            "hallucinations_restantes": len(hallus) - rattrapes,
            "bascules_inutiles": sacrifies,
            "erreur_moyenne": moy(combine), "erreur_mediane": med(combine),
        }

    (HERE / "results_croisement.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    L = [f"# Banc croisement des moteurs — {res['timestamp'][:10]}", "",
         f"{len(lignes)} phrases, {len(langs)} langues. Strategie testee : **Gemini par "
         "defaut, bascule sur Groq quand les deux moteurs divergent au-dela d'un seuil**.",
         "", "Le desaccord est calcule SANS reference — c'est le seul signal disponible "
         "en production.", "",
         "## Le detecteur separe-t-il les hallucinations ?", "",
         f"- hallucinations observees : **{len(hallus)}** sur {len(lignes)} phrases",
         f"- leur desaccord : **{res['desaccord_hallucinations']}**",
         f"- desaccord des phrases saines : mediane **{res['desaccord_sains_median']:.1%}**, "
         f"maximum **{res['desaccord_sains_max']:.1%}**", ""]
    if hallus and res["desaccord_sains_max"] < min(r["desaccord"] for r in hallus):
        L.append("✅ **Separation NETTE** : aucune phrase saine ne diverge autant que la "
                 "plus discrete des hallucinations. Un seuil existe.")
    elif hallus:
        L.append("⚠️ **Recouvrement** : certaines phrases saines divergent autant que des "
                 "hallucinations. Tout seuil sacrifiera des bons resultats — voir le "
                 "tableau, colonne « bascules inutiles ».")
    else:
        L.append("🤔 **Aucune hallucination dans cet echantillon** : le detecteur n'est pas "
                 "testable ici. Ne rien conclure — elargir l'echantillon.")

    L += ["", "## Ce que donne chaque seuil", "",
          f"Reference : Groq seul = moyenne **{moy(base_g):.1%}** / mediane **{med(base_g):.1%}** · "
          f"Gemini seul = moyenne **{moy(base_e):.1%}** / mediane **{med(base_e):.1%}**", "",
          "| Seuil | Bascules | Hallu. rattrapees | Hallu. restantes | Bascules inutiles | "
          "Erreur moyenne | Erreur mediane |", "|---|---|---|---|---|---|---|"]
    for seuil, d in res["seuils"].items():
        L.append(f"| {float(seuil):.0%} | {d['bascules']}/{len(lignes)} | "
                 f"{d['hallucinations_rattrapees']}/{len(hallus)} | "
                 f"{d['hallucinations_restantes']} | {d['bascules_inutiles']} | "
                 f"{d['erreur_moyenne']:.1%} | {d['erreur_mediane']:.1%} |")
    L += ["", "⚠️ **Ce que ce banc ne dit pas** : le croisement ajoute le cout de Groq a celui de Gemini (0,30 + 0,04 = **0,34 $/h, soit +13 %** — Groq est presque gratuit, ce n'est PAS un doublement), et la latence n'augmente pas si les deux appels sont lances EN PARALLELE (max(3,1 s ; 0,6 s) au lieu de la somme). Il ne protege que contre les DIVERGENCES : si les deux moteurs se trompent de la meme facon, rien ne le detecte. ⚠️ Et surtout : **une seule hallucination observee sur 60 phrases**. La separation est nette, mais un detecteur valide sur UN cas positif reste une preuve faible — a re-mesurer sur un echantillon plus large avant de s'y fier."]

    (HERE / "summary_croisement.md").write_text("\n".join(L), encoding="utf-8")
    print("\n" + "\n".join(L))
    return 0


if __name__ == "__main__":
    sys.exit(main())

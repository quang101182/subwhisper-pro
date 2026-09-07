# Banc STT multilingue SubWhisper — 2026-09-07

10 samples/langue, dataset FLEURS (Google, open). Metriques NORMALISEES (casse + ponctuation retirees).

⚠️ **Le chinois, le japonais et le coreen se lisent sur le CER**, pas le WER : ces langues n'ecrivent pas d'espaces entre les mots, un WER y mesurerait la segmentation et non la reconnaissance.

⚠️ **Lire la MEDIANE autant que la moyenne.** Une seule phrase ou le modele hallucine (score > 100 % = il a AJOUTE du texte) suffit a doubler une moyenne et a inverser un classement. La colonne `halluc.` compte ces cas.

| Langue | Metrique | Modele | Moyenne | Mediane | halluc. | pire | Latence | $/h |
|---|---|---|---|---|---|---|---|---|
| Francais | WER | `whisper-large-v3-turbo` | 12.0% | 13.0% | 0 | 29% | 0.64s | $0.04 |
| Francais | WER | `gemini-3.5-transcribe` | 6.2% | 1.1% | 0 | 19% | 3.13s | $0.30 |
| Anglais | WER | `whisper-large-v3-turbo` | 4.5% | 4.6% | 0 | 11% | 0.64s | $0.04 |
| Anglais | WER | `gemini-3.5-transcribe` | 3.2% | 2.2% | 0 | 10% | 3.06s | $0.30 |
| Allemand | WER | `whisper-large-v3-turbo` | 3.8% | 4.4% | 0 | 11% | 0.73s | $0.04 |
| Allemand | WER | `gemini-3.5-transcribe` | 1.9% | 0.0% | 0 | 6% | 3.34s | $0.30 |
| Chinois | CER | `whisper-large-v3-turbo` | 6.8% | 3.7% | 0 | 27% | 0.67s | $0.04 |
| Chinois | CER | `gemini-3.5-transcribe` | 16.0% | 0.0% | 1 | 141% | 3.12s | $0.30 |
| Japonais | CER | `whisper-large-v3-turbo` | 6.6% | 7.2% | 0 | 16% | 0.61s | $0.04 |
| Japonais | CER | `gemini-3.5-transcribe` | 1.7% | 0.0% | 0 | 14% | 3.09s | $0.30 |
| Coreen | CER | `whisper-large-v3-turbo` | 4.2% | 2.8% | 0 | 21% | 0.60s | $0.04 |
| Coreen | CER | `gemini-3.5-transcribe` | 2.6% | 1.2% | 0 | 10% | 3.49s | $0.30 |

## Verdict par langue

### Francais (sur WER)
- `gemini-3.5-transcribe` : WER moyen -5.8 pt (MIEUX, +48 % relatif), latence x4.9, cout x7.5
  - sur la MEDIANE : -11.9 pt (MIEUX) — 0 hallucination(s) contre 0 pour la baseline

### Anglais (sur WER)
- `gemini-3.5-transcribe` : WER moyen -1.3 pt (MIEUX, +28 % relatif), latence x4.8, cout x7.5
  - sur la MEDIANE : -2.5 pt (MIEUX) — 0 hallucination(s) contre 0 pour la baseline

### Allemand (sur WER)
- `gemini-3.5-transcribe` : WER moyen -1.9 pt (MIEUX, +50 % relatif), latence x4.6, cout x7.5
  - sur la MEDIANE : -4.4 pt (MIEUX) — 0 hallucination(s) contre 0 pour la baseline

### Chinois (sur CER)
- `gemini-3.5-transcribe` : CER moyen +9.2 pt (PIRE, -135 % relatif), latence x4.7, cout x7.5
  - sur la MEDIANE : -3.7 pt (MIEUX) — 1 hallucination(s) contre 0 pour la baseline

### Japonais (sur CER)
- `gemini-3.5-transcribe` : CER moyen -4.9 pt (MIEUX, +74 % relatif), latence x5.1, cout x7.5
  - sur la MEDIANE : -7.2 pt (MIEUX) — 0 hallucination(s) contre 0 pour la baseline

### Coreen (sur CER)
- `gemini-3.5-transcribe` : CER moyen -1.6 pt (MIEUX, +39 % relatif), latence x5.8, cout x7.5
  - sur la MEDIANE : -1.5 pt (MIEUX) — 0 hallucination(s) contre 0 pour la baseline

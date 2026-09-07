# Banc timestamps SubWhisper — 2026-09-07

6 phrases Francais concatenees (71.6s), separees par 0.8s de silence. Les frontieres sont donc EXACTES par construction.

Ecart = distance entre chaque frontiere connue et le debut d'unite le plus proche rendu par le moteur.

| Moteur | Unite | Nb | Ecart moyen | Median | Pire | <=200ms | <=500ms | Latence |
|---|---|---|---|---|---|---|---|---|
| `groq_whisper_turbo` | segment | 12 | 170 ms | 130 ms | 380 ms | 4/6 | 6/6 | 1.57s |
| `gemini_35_transcribe` | mot | 170 | 420 ms | 30 ms | 2040 ms | 4/6 | 5/6 | 6.36s |

⚠️ Un silence net entre phrases est un cas FACILE : ce banc mesure un plancher de qualite, pas le comportement sur parole continue ou dialogue qui se chevauche.

⚠️ Chez Gemini, `timestamp_granularities:["segment"]` ne rend AUCUN timestamp (mesure du 07/09) : c'est le MOT ou rien. Et `custom_vocabulary` est incompatible avec les timestamps — il faut choisir entre le calage et les noms propres.
# Comparatif moteurs STT SubWhisper — Groq Turbo vs Gemini 3.5 Transcribe

> Mesures du **07/09/2026**. Demande de Quang : *« ce serait une évolution de
> l'application où je peux choisir quel moteur je vais utiliser en conservant celui
> d'aujourd'hui aussi. Et bien sûr, avant de faire quoi que ce soit, il faut que tu
> fasses un vrai comparatif. »*
>
> **Ce document mesure. Il ne décide pas, et rien n'a été implémenté.**
> Zéro ligne touchée dans `app.html`. Deux bancs neufs dans `tools/`.

## 0. Le résumé en trois lignes

**Gemini 3.5 Transcribe est meilleur que Groq Turbo sur les 6 langues de ton usage,
et l'écart est large** — le français passe de 13,0 % à 1,1 % d'erreur médiane.
**Mais il est moins régulier** : il décroche parfois franchement, là où Groq se
trompe peu mais tout le temps. C'est vrai du texte ET du calage des sous-titres.
⇒ Un **choix de moteur** est exactement la bonne réponse. Un remplacement, non.

## 1. Ce qui tourne aujourd'hui — et une surprise

Le moteur réel de SubWhisper est `whisper-large-v3-turbo` chez Groq, et c'est le
**seul chemin atteignable** : les branches OpenAI et AssemblyAI existent dans le
code mais tous les getters de clés renvoient `''` en dur (`app.html:1989-2009`),
et AssemblyAI est appelé en direct sur `AAI_BASE`, pas via la gateway.

⚠️ **Conséquence non anticipée, vérifiée ligne à ligne** : la case à cocher
**« Speaker detection »** (`app.html:1352`) n'est lue qu'à **une seule ligne**,
`app.html:2256`, dans le corps de la branche AssemblyAI — donc **jamais atteinte**.
La case est cochable, elle se mémorise dans `localStorage`, et **elle ne fait
rien**. Idem pour la **vue RICH** (mot à mot cliquable) : son bouton est `disabled`
tant que `wordData` est vide (`app.html:3497`), et `wordData` n'est rempli que par
AssemblyAI. **Ces deux fonctions sont mortes dans l'app telle qu'elle tourne.**

📌 Bug annexe repéré au passage : `transcribeOpenAI()` étiquette son résultat
`_diagSteps.transcription_engine = 'assemblyai'` (`app.html:2458`). Les DIAG
exportés attribuent donc les transcriptions OpenAI au mauvais moteur.

## 2. Qualité par langue — FLEURS, 10 phrases/langue

⚠️ **Le chinois, le japonais et le coréen se lisent en CER, pas en WER.** Ces
langues n'écrivent pas d'espaces entre les mots : un WER y mesurerait la
segmentation, pas la reconnaissance. Deux transcriptions correctes découpées
différemment donneraient 100 % d'erreur.

⚠️ **Lire la médiane autant que la moyenne** — voir § 3, c'est tout le sujet.

| Langue | Métrique | Groq Turbo | | **Gemini 3.5** | | halluc. |
|---|---|---|---|---|---|---|
| | | moyenne | médiane | moyenne | médiane | |
| 🇫🇷 Français | WER | 12,0 % | 13,0 % | **6,2 %** | **1,1 %** | 0 |
| 🇬🇧 Anglais | WER | 4,5 % | 4,6 % | **3,2 %** | **2,2 %** | 0 |
| 🇩🇪 Allemand | WER | 3,8 % | 4,4 % | **1,9 %** | **0,0 %** | 0 |
| 🇨🇳 Chinois | CER | 6,8 % | 3,7 % | 16,0 % ⚠️ | **0,0 %** | **1** |
| 🇯🇵 Japonais | CER | 6,6 % | 7,2 % | **1,7 %** | **0,0 %** | 0 |
| 🇰🇷 Coréen | CER | 4,2 % | 2,8 % | **2,6 %** | **1,2 %** | 0 |

**Gemini gagne sur la médiane dans les 6 langues, sans exception.** Trois d'entre
elles (allemand, chinois, japonais) ressortent à **0,0 % d'erreur médiane** : plus
d'une phrase sur deux est transcrite parfaitement.

Le gain est le plus spectaculaire là où Groq est le plus faible : **français**
(13,0 → 1,1) et **japonais** (7,2 → 0,0).

## 3. Le défaut de Gemini, et il est structurel : l'hallucination

La moyenne chinoise de Gemini (16,0 %) contredit sa médiane (0,0 %). Ce n'est pas
un artefact de mesure — j'ai vérifié les 10 phrases une par une :

| Phrase | Groq | Gemini |
|---|---|---|
| 1-8, 10 | 0-17 % | **0-11 %, il gagne 8 fois sur 10** |
| **9** | 27 % | **140,5 %** |

Sur la phrase 9, l'audio dit « Scotturb 403 路公共汽车… 辛特拉 Sintra… 罗卡角 ».
Gemini rend :

> Scott**sbluff** 403 路公交汽车定期发车前往**斯科茨布拉夫国家纪念碑 (Scottsbluff
> National Monument)** 的罗卡角 **(Mitchell Pass)** 停靠。

Il ne s'est pas trompé sur un caractère : **il a inventé un monument américain et
un col de montagne qui ne sont pas dans l'audio.** Un CER > 100 % signifie
exactement ça — le modèle a AJOUTÉ du texte.

⇒ **Pour un sous-titre, c'est pire qu'une faute.** Une erreur de caractère se
repère et se corrige ; une phrase plausible mais fausse passe inaperçue. C'est
précisément le risque qu'un moteur « intelligent » fait courir : Gemini nettoie,
reformule et complète — et parfois il complète ce qu'il n'a pas entendu.

Groq Turbo, lui, n'a produit **aucune hallucination** sur les 60 phrases.

## 4. Le calage des sous-titres — le critère que le WER ignore

Un texte parfait posé 300 ms trop tôt est inutilisable. Banc dédié : 6 phrases
françaises concaténées (71,6 s) séparées par 0,8 s de silence, donc des frontières
**exactes par construction**.

| Moteur | Unité | Nb | Écart moyen | **Médiane** | Pire | ≤ 200 ms | ≤ 500 ms |
|---|---|---|---|---|---|---|---|
| Groq Turbo | segment | 12 | 170 ms | 130 ms | 380 ms | 4/6 | **6/6** |
| **Gemini 3.5** | **mot** | **170** | 420 ms | **30 ms** | 2040 ms | 4/6 | 5/6 |

**Le même pattern, sur un axe totalement différent** : Gemini est 4× plus précis en
médiane (30 ms contre 130 ms) mais produit un décrochage à 2 s. Groq ne descend
jamais très bas et ne dérape jamais.

🔑 **Le fait le plus important de ce tableau n'est pas un chiffre, c'est une
colonne** : Gemini rend **170 mots** là où Groq rend **12 segments**. Gemini fournit
des timestamps **au mot** — ce que SubWhisper n'a plus depuis qu'AssemblyAI est
inatteignable. Cela **ressusciterait la vue RICH et la diarisation** (§ 1) sur le
chemin réellement utilisé.

⛔ **Le piège de mesure qui a invalidé ma première version de ce banc** (gardé ici
pour qu'il ne soit pas repayé) : les clips FLEURS commencent par ~2 s de silence.
En prenant le début de clip comme frontière, je mesurais ce silence et les deux
moteurs ressortaient à 0,8-1,2 s — un résultat qui ne voulait rien dire. La vérité
terrain d'un timestamp de parole, c'est le début de la **parole** (`debut_parole()`).

## 5. Ce que l'API impose — vérifié en direct, rien de supposé

1. ✅ **Ça passe par la gateway sans rien changer** : `/api/gemini/*` proxifie déjà
   n'importe quel sous-chemin avec `GEMINI_KEY` en KV. Aucune clé côté client.
2. ⛔ **Deux fonctions s'excluent** : `custom_vocabulary` est **incompatible avec la
   diarisation et les timestamps** (doc Google). Il faut choisir : **noms propres
   OU calage**. Pour SubWhisper, le calage gagne — donc pas de vocabulaire.
3. ⛔ **Chez Gemini, `timestamp_granularities: ["segment"]` ne rend AUCUN
   timestamp** (mesuré) : c'est **le mot ou rien**. Il faudra donc **reconstruire
   les segments SRT à partir des mots** — `autoFormatSRT()` (`app.html:5071`, règles
   42 car./2 lignes/25 CPS) sait déjà le faire, mais il faudra l'alimenter autrement.
4. ⚠️ **Diarisation plafonnée à 3 locuteurs** (au-delà = expérimental).
5. ⚠️ **Le mode `smart` reformule** : il supprime les hésitations et la ponctuation
   parasite. Excellent pour un compte-rendu, **discutable pour un sous-titre**, qui
   doit coller à ce qui est dit. Le mode `verbatim` existe pour ça — c'est celui à
   utiliser, et c'est aussi le seul qui donne les timestamps.
6. ⛔ **Le `-live` ne passe pas** : WebSocket, la gateway n'en fait aucun. Hors sujet
   pour SubWhisper (qui travaille sur fichier), mais à savoir.
7. 🟠 Statut **preview (blog Google) vs GA (changelog API)** : contradiction non levée.
   À trancher avant de s'appuyer dessus dans SubWhisper **Pro**, qui est payant.

## 6. Coût

$0,005/min = **$0,30/h** contre **$0,04/h** pour Groq Turbo, soit **×7,5**.
Sur une vidéo d'une heure : **$0,30 au lieu de $0,04**. En usage personnel c'est
négligeable ; sur SubWhisper Pro facturé à l'usage, ça se regarde avant, pas après.

📌 Ordre de grandeur : le péage fixe de ~2,8 s par appel (mesuré dans le verdict
DictoKey) est **amorti** ici — sur un fichier long découpé en chunks de ~13 min
(`MAX_BYTES = 24 Mo`, `app.html:2503`), il ne s'applique qu'une fois par chunk.

## 7. Ce que je recommande — et ce qui reste à décider

**Le choix de moteur que tu décris est la bonne architecture**, et pour une raison
que le comparatif rend explicite : aucun des deux moteurs ne domine l'autre sur
tous les axes. Groq = rapide, régulier, gratuit ou presque. Gemini = nettement plus
juste, timestamps au mot, mais 7,5× plus cher et capable d'inventer une phrase.

Le chemin le plus court, si tu veux qu'on le fasse (rien n'est commencé) :
- un `<select id="sttEngine">` sur le patron **exact** de `aiEngine`
  (`app.html:1574-1577`, `getAIEngine()` 1993, `saveAIEngine()` 2003, clé
  `localStorage` symétrique `sw_sttengine`) ;
- **Groq reste le défaut**, Gemini est un choix explicite ;
- un `transcribeGemini()` calqué sur `transcribeGroq()` (`app.html:2490-2643`),
  respectant le contrat de retour `{ srt, lang, segments, rawSegments }` (2862) ;
- l'insertion se fait à **une seule ligne** : la cascade `app.html:2225-2227`.

🟠 **Trois questions ouvertes, qui sont pour toi, pas pour moi :**
1. **Le risque d'hallucination est-il acceptable** pour tes sous-titres ? C'est le
   seul vrai point noir, et il est silencieux par nature.
2. **PRO ou APP d'abord ?** Les deux ont divergé : PRO propose **74 langues**
   (`app.html:1196-1347`), APP seulement **16** (`index.html:1179-1197`), et ils
   pointent sur **deux gateways différentes** (`api-gateway-pro` vs `api-gateway`).
3. **Répare-t-on la diarisation morte** (§ 1) au passage ? Gemini la rendrait
   possible sur le chemin réel — mais pas en même temps que le vocabulaire.

## Reproduire

```bash
cd subwhisper-pro
python tools/bench_stt_multilingue.py --samples 10          # 6 langues
python tools/bench_timestamps.py --phrases 6                # calage
```

⚠️ Les corpus FLEURS (424-692 Mo/langue) se téléchargent tout seuls dans
`dictokey/tools/fleurs/` (partagés avec le banc DictoKey, gitignorés). Le streaming
HuggingFace ne fonctionne plus : le parquet publié n'a qu'un seul row group, donc
lire la première ligne revient à tout télécharger.

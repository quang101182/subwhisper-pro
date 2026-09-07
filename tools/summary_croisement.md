# Banc croisement des moteurs — 2026-09-07

60 phrases, 6 langues. Strategie testee : **Gemini par defaut, bascule sur Groq quand les deux moteurs divergent au-dela d'un seuil**.

Le desaccord est calcule SANS reference — c'est le seul signal disponible en production.

## Le detecteur separe-t-il les hallucinations ?

- hallucinations observees : **1** sur 60 phrases
- leur desaccord : **[1.9]**
- desaccord des phrases saines : mediane **2.7%**, maximum **20.5%**

✅ **Separation NETTE** : aucune phrase saine ne diverge autant que la plus discrete des hallucinations. Un seuil existe.

## Ce que donne chaque seuil

Reference : Groq seul = moyenne **6.3%** / mediane **4.5%** · Gemini seul = moyenne **5.3%** / mediane **0.0%**

| Seuil | Bascules | Hallu. rattrapees | Hallu. restantes | Bascules inutiles | Erreur moyenne | Erreur mediane |
|---|---|---|---|---|---|---|
| 20% | 2/60 | 1/1 | 0 | 1 | 3.7% | 0.0% |
| 30% | 1/60 | 1/1 | 0 | 0 | 3.4% | 0.0% |
| 40% | 1/60 | 1/1 | 0 | 0 | 3.4% | 0.0% |
| 50% | 1/60 | 1/1 | 0 | 0 | 3.4% | 0.0% |
| 60% | 1/60 | 1/1 | 0 | 0 | 3.4% | 0.0% |

⚠️ **Ce que ce banc ne dit pas** : le croisement ajoute le cout de Groq a celui de Gemini (0,30 + 0,04 = **0,34 $/h, soit +13 %** — Groq est presque gratuit, ce n'est PAS un doublement), et la latence n'augmente pas si les deux appels sont lances EN PARALLELE (max(3,1 s ; 0,6 s) au lieu de la somme). Il ne protege que contre les DIVERGENCES : si les deux moteurs se trompent de la meme facon, rien ne le detecte. ⚠️ Et surtout : **une seule hallucination observee sur 60 phrases**. La separation est nette, mais un detecteur valide sur UN cas positif reste une preuve faible — a re-mesurer sur un echantillon plus large avant de s'y fier.

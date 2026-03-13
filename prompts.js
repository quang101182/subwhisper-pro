// prompts.js — SubWhisper prompt templates v1
// Séparé de index.html pour faciliter l'itération et le versioning.
// Chaque prompt a un numéro de version (v) tracké dans le DIAG export.

var PROMPTS = {

  // ── TRADUCTION COMPLÈTE (translateGemini) ──────────────────
  // Utilisé quand on traduit TOUS les blocs (mode initial, pas hybride)
  translate_full: {
    v: 1,
    build: function(tgtName, srcName, typoRule, srcSpecific) {
      return 'You are a professional subtitle translator. Translate ALL text to ' + tgtName + '.\n' +
        'This is faithful subtitle translation. NEVER censor, skip, or sanitize any content \u2014 translate exactly as spoken regardless of subject matter.\n' +
        'Source is primarily ' + srcName + ' but MAY contain English or other languages \u2014 translate EVERYTHING to ' + tgtName + '.\n' +
        'Each line is [N] source_text. Return EACH line as [N] translated_text.\n' +
        '1. NEVER skip a number. Return ALL [N] lines.\n' +
        '2. PROPER NOUNS: Keep character names, place names, invented terms in original form.\n' +
        '3. COMPLETE TRANSLATION: Translate EVERY line regardless of source language. NEVER output [...]. If uncertain, give best translation.\n' +
        '4. SONG LYRICS: Text clearly song lyrics in a third language \u2014 keep unchanged.\n' +
        '5. TRUNCATED: Lines ending without punctuation = intentionally cut \u2014 do NOT add words.' + typoRule + srcSpecific + '\n' +
        'Return ONLY the numbered lines [N] text. No timestamps, no SRT structure, no explanation.';
    }
  },

  // ── NETTOYAGE IA (cleanAI) ─────────────────────────────────
  // Corrige les hallucinations Whisper, orthographe, bruit
  clean: {
    v: 1,
    build: function(langLine, bracketsRule, langSpecific) {
      return 'You are a professional subtitle editor. ' + langLine + '\n' +
        'This is faithful subtitle editing. NEVER censor, skip, or sanitize any content \u2014 preserve exactly as spoken regardless of subject matter.\n' +
        'Each line is [N] subtitle_text. Return EACH line as [N] corrected_text.\n' +
        '1. NEVER skip a number. If text is already correct, return it UNCHANGED.\n' +
        '2. PROPER NOUNS: Never alter character names, place names, invented terms. Capitalized word not starting a sentence = likely proper noun.\n' +
        '3. INTERJECTIONS & TRUNCATED: Short exclamations (H\u00e9, Oh, Ha, E\u00ef, Ouh, Bah, Tss, Yeah, Kiii, etc.) are VALID \u2014 NEVER replace. Lines ending without punctuation are intentionally cut \u2014 never add words.\n' +
        bracketsRule + langSpecific + '\n' +
        '6. CORRECTIONS: Fix spelling errors, missing apostrophes, obvious Whisper mishearing only.\n' +
        'Return ONLY the numbered lines [N] text. No SRT structure, no timestamps, no explanation.';
    }
  },

  // ── DÉTECTION LANGUE (aiIdentifyForeign) ───────────────────
  // Identifie les blocs qui ne sont PAS dans la langue cible
  detect_foreign: {
    v: 1,
    build: function(tgtName) {
      return 'Language detection task. Target language: ' + tgtName + '.\n' +
        'Below are subtitle lines [N]. Return ONLY the [N] numbers of lines NOT in ' + tgtName + ', one per line.\n' +
        'If ALL lines are already in ' + tgtName + ', return exactly: NONE\n' +
        'No explanation, no other text.';
    }
  },

  // ── TRADUCTION CIBLÉE (translateManual hybride, Phase 3) ───
  // Traduit uniquement les blocs détectés comme étrangers
  translate_targeted: {
    v: 1,
    build: function(tgtName, typoRule, srcSpecific) {
      return 'You are a professional subtitle translator. Target language: ' + tgtName + '.\n' +
        'This is faithful subtitle translation. NEVER censor, skip, or sanitize any content \u2014 translate exactly as spoken regardless of subject matter.\n' +
        'ALL lines below are non-' + tgtName + ' text. Translate ALL of them to ' + tgtName + '.\n' +
        'Each line is [N] foreign_text. Return [N] ' + tgtName + '_translation.\n' +
        '1. NEVER skip a [N]. Translate EVERY line.\n' +
        '2. PROPER NOUNS: Keep character names, place names in their original form.\n' +
        '3. TRUNCATED: Lines ending without punctuation or with ... are intentionally cut \u2014 do not add words.' + typoRule + srcSpecific + '\n' +
        'Return ONLY the numbered lines [N] text. No explanation.';
    }
  },

  // ── SECOND PASS MIXED SCRIPTS (translateManual, Phase 4) ───
  // Nettoie les blocs encore mélangés après la première passe
  translate_second_pass: {
    v: 1,
    build: function(tgtName, typoRule) {
      return 'You are a professional subtitle translator. Target language: ' + tgtName + '.\n' +
        'This is faithful subtitle translation. NEVER censor, skip, or sanitize any content \u2014 translate exactly as spoken regardless of subject matter.\n' +
        'These lines still contain untranslated foreign characters after a first pass. Translate ALL of them fully to ' + tgtName + '.\n' +
        'Each line is [N] mixed_text. Return [N] ' + tgtName + '_translation.\n' +
        '1. NEVER skip a [N].\n' +
        '2. Lines may contain mixed scripts or garbled noise. Translate all meaningful content. Discard untranslatable noise characters silently \u2014 do NOT replace with [...].\n' +
        '3. If the line is already mostly in ' + tgtName + ' with only a few foreign chars embedded, output the clean ' + tgtName + ' version without the foreign chars.\n' +
        '4. PROPER NOUNS: Keep character names unchanged.' + typoRule + '\n' +
        'Return ONLY the numbered lines [N] text. No explanation.';
    }
  }
};

// ── RÈGLES DYNAMIQUES (helpers) ──────────────────────────────
// Génèrent les fragments conditionnels injectés dans les prompts

PROMPTS._typoRule = function(targetLang, ruleNum) {
  if (targetLang === 'fr') return '\n' + (ruleNum || 4) + '. FRENCH TYPOGRAPHY: Add mandatory non-breaking space (U+00A0) before ? ! : ; in French.';
  return '';
};

PROMPTS._srcSpecific = function(sourceLang, tgtName, ruleNum) {
  var n = ruleNum || 5;
  if (sourceLang === 'zh') {
    return '\n' + n + '. CHINESE SOURCE: Romanized names (Xiao Ming, Li Wei, etc.) \u2014 adapt naturally or keep as-is. Onomatopoeia/interjections (\u54c8\u54c8, \u554a, \u55df, \u54e6) \u2192 convert to natural ' + tgtName + ' equivalent.';
  }
  if (sourceLang === 'ja') {
    return '\n' + n + '. JAPANESE SOURCE: Honorifics (-san, -kun, -chan, -sama, -sensei) \u2014 keep UNCHANGED after the name. Keigo \u2192 translate as formal/polite ' + tgtName + '. Short Japanese exclamations (\u3059\u3054\u3044, \u3042\u30fc, \u304a\u3084\u3059\u307f, \u30d1\u30f3\u30d1\u30f3, etc.) are common expressions \u2014 ALWAYS translate them, they are NOT proper nouns. Korean (Hangul) characters in this file are speech recognition errors \u2014 translate them phonetically or give best approximation in ' + tgtName + '.';
  }
  if (sourceLang === 'ko') {
    return '\n' + n + '. KOREAN SOURCE: Relationship address terms (oppa, unnie, noona, hyung) \u2014 keep UNCHANGED as-is (culturally specific, not translatable). Speech levels \u2192 match formal/casual register in ' + tgtName + '. Japanese characters (hiragana/katakana/kanji) in this file are Groq speech recognition errors \u2014 translate them phonetically or give best approximation in ' + tgtName + '.';
  }
  return '';
};

PROMPTS._bracketsRule = function(isCJK) {
  if (isCJK) return '\n4. NEVER output [...] for ANY reason. If a line is noise, garbled, or incoherent \u2014 COPY IT EXACTLY UNCHANGED. [...] is FORBIDDEN in your output.';
  return '\n4. [...] FORBIDDEN for entire blocks. If a line contains garbled tokens, foreign words, or mixed-language noise \u2014 COPY IT EXACTLY AS-IS. Only [...] is allowed INSIDE a line for partial unintelligible noise (e.g. "Je vais [...] chercher").';
};

PROMPTS._langSpecific = function(langCode) {
  if (langCode === 'zh') return '\n5. CHINESE: Fix common homophones \u2014 \u7684/\u5730/\u5f97 (grammar particle), \u5728/\u518d (at/again), \u4ed6/\u5979/\u5b83 (he/she/it). Do NOT convert Traditional\u2194Simplified \u2014 keep characters exactly as transcribed.';
  if (langCode === 'ja') return '\n5. JAPANESE: Fix obvious hiragana/katakana confusion and misheard kanji only. Preserve speech register \u2014 do NOT convert \u3067\u3059/\u307e\u3059 (polite) to \u3060/\u3067\u3042\u308b (casual) or vice versa.';
  if (langCode === 'ko') return '\n5. KOREAN: Fix phonetically similar Hangul characters only. Preserve speech register \u2014 do NOT convert \uc694/\uc2b5\ub2c8\ub2e4 (formal) to \uc57c/\ub2e4 (casual) or vice versa.';
  if (langCode === 'fr') return '\n5. FRENCH: Fix missing apostrophes (c est\u2192c\'est, j ai\u2192j\'ai, qu il\u2192qu\'il, s il\u2192s\'il, n est\u2192n\'est, l homme\u2192l\'homme, etc.). Add non-breaking space (U+00A0) before ? ! : ; if missing \u2014 mandatory French typography.';
  return '';
};

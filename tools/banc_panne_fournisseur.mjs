// Banc — SubWhisper Pro v1.3.2 : une panne du fournisseur IA ne pend plus et ne passe plus inaperçue.
//
// Incident du 14/09/2026 au soir : DeepSeek Flash saturé mettait chaque requête EN FILE sans erreur (flux :
// « : keep-alive » toutes les 12 s). callAIText n'avait aucun délai : chaque lot attendait indéfiniment.
// Ce banc EXTRAIT les vraies fonctions de app.html (_aiEtat, _aiErreurFournisseur, _aiLireFluxDeepSeek,
// callAIText) et les exécute dans Node face à un FAUX fournisseur, délais raccourcis :
//   A. flux normal → texte rendu, bumpUsage('translation') compté UNE fois
//   B. en file (keep-alive seuls) → erreur .fournisseur « queued » en quelques secondes, usage NON compté
//   C. muet (aucun en-tête) → erreur .fournisseur
//   D. génération lente mais active → rendue, jamais coupée
//   E. génération coupée → erreur .fournisseur « generation stopped »
//   F. 429 répété → erreur .fournisseur (après 1 retry)
//   G. fast-fail : juste après une panne, l'appel suivant échoue en moins de 50 ms sans fetch
//   H. Gemini : délai total → erreur .fournisseur ; réponse normale → texte + usage
//   I. MUTATION : keep-alive compté comme une réponse → B doit rougir
// Sans réseau, sans clé.     node tools/banc_panne_fournisseur.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import vm from 'node:vm';

const ICI = dirname(fileURLToPath(import.meta.url));
const SOURCE = readFileSync(join(ICI, '..', 'app.html'), 'utf8');

function extraire(src, nom) {
  const lignes = src.split('\n');
  const debut = lignes.findIndex(l => new RegExp(`^(async\\s+)?function\\s+${nom}\\s*\\(`).test(l));
  if (debut < 0) throw new Error(`fonction ${nom} introuvable dans app.html`);
  const fin = lignes.findIndex((l, i) => i > debut && l.replace(/\r$/, '') === '}');
  return lignes.slice(debut, fin + 1).join('\n');
}

const FONCTIONS = ['_aiEtat', '_aiErreurFournisseur', '_aiLireFluxDeepSeek', 'callAIText'];

function contexte(source, mode, moteur = 'deepseek') {
  const journal = { toasts: [], usage: 0, fetchs: 0 };
  const enc = new TextEncoder();
  const faux = async (url, opts) => {
    journal.fetchs++;
    const signal = opts && opts.signal;
    const abandon = ko => signal && signal.addEventListener('abort', () => ko(Object.assign(new Error('aborted'), { name: 'AbortError' })));
    if (mode === 'muet') return new Promise((_, ko) => abandon(ko));
    if (mode === '429') return { ok: false, status: 429, statusText: 'Too Many', json: async () => ({ error: { message: 'rate limit' } }) };
    if (mode === 'corps503') return { ok: false, status: 503, statusText: 'Service Unavailable', json: () => new Promise((_, ko) => abandon(ko)) };
    if (moteur === 'gemini') {
      if (mode === 'gemini-muet') return new Promise((_, ko) => abandon(ko));
      return { ok: true, status: 200, json: async () => ({ candidates: [{ content: { parts: [{ text: 'Bonjour' }] } }] }) };
    }
    const minuteurs = [];
    const body = new ReadableStream({
      start(c) {
        const fermer = () => minuteurs.forEach(clearInterval);
        const envoyer = t => { try { c.enqueue(enc.encode(t)); } catch (_) { fermer(); } };
        if (signal) signal.addEventListener('abort', () => { fermer(); try { c.error(new Error('aborted')); } catch (_) {} });
        envoyer(': keep-alive\n\n');
        if (mode === 'file') { minuteurs.push(setInterval(() => envoyer(': keep-alive\n\n'), 200)); return; }
        const parts = ['Bon', 'jour'];
        let i = 0, ouvert = false;
        minuteurs.push(setInterval(() => {
          if (ouvert) { envoyer(': keep-alive\n\n'); return; }
          if (mode === 'coupure' && i >= 1) { envoyer(': keep-alive\n\n'); return; }
          if (mode === 'tronque' && i >= 1) { fermer(); try { c.close(); } catch (_) {} return; }
          if (i < parts.length) envoyer('data: ' + JSON.stringify({ choices: [{ index: 0, delta: { content: parts[i++] } }] }) + '\n\n');
          else { envoyer('data: [DONE]\n\n'); if (mode === 'done-ouvert') { ouvert = true; return; } fermer(); try { c.close(); } catch (_) {} }
        }, mode === 'lent' ? 700 : 20));
      },
    });
    return { ok: true, status: 200, body, json: async () => ({}) };
  };
  const ctx = {
    console, setTimeout, clearTimeout, setInterval, clearInterval, TextDecoder, TextEncoder, AbortController, Date, JSON, Math, Error, TypeError, Promise,
    fetch: faux,
    GATEWAY_URL: 'https://gw.test',
    getAIEngine: () => moteur, getDeepSeekKey: () => '', getGeminiKey: () => '', getGatewayKey: () => 'swp_banc',
    toastPersist: m => journal.toasts.push(m),
    bumpUsage: t => { if (t === 'translation') journal.usage++; },
  };
  vm.createContext(ctx);
  vm.runInContext(FONCTIONS.map(n => extraire(source, n)).join('\n') + '\n_aiEtat().delais = { premier: 1500, silence: 2000, total: 3000, memoire: 90000 };', ctx);
  return { ctx, journal };
}

async function essai(mode, { source = SOURCE, moteur = 'deepseek' } = {}) {
  const { ctx, journal } = contexte(source, mode, moteur);
  const t0 = Date.now();
  try {
    const texte = await ctx.callAIText('[1] 你好');
    return { ok: true, texte, s: (Date.now() - t0) / 1000, journal, ctx };
  } catch (e) {
    return { ok: false, err: e, s: (Date.now() - t0) / 1000, journal, ctx };
  }
}

async function scenario(source = SOURCE) {
  const R = [];
  const ok = (nom, cond, det = '') => R.push([nom, !!cond, det]);
  const a = await essai('flux', { source });
  ok('A. flux normal : texte rendu, usage compté une fois', a.ok && a.texte === 'Bonjour' && a.journal.usage === 1, JSON.stringify({ t: a.texte, u: a.journal.usage, e: a.err?.message }));
  const b = await essai('file', { source });
  ok('B. en file : erreur fournisseur « queued » en < 6 s, usage non compté',
     !b.ok && b.err.fournisseur && /queued/.test(b.err.message) && b.s < 6 && b.journal.usage === 0 && b.journal.toasts.length === 1,
     `${b.s}s ${b.err?.message}`);
  const c = await essai('muet', { source });
  ok('C. muet : erreur fournisseur', !c.ok && c.err.fournisseur, `${c.s}s ${c.err?.message}`);
  const c2 = await essai('corps503', { source });
  ok('C. 503 dont le corps ne se termine jamais : erreur fournisseur, ne pend plus', !c2.ok && c2.err.fournisseur && c2.s < 6,
     `${c2.s}s ${c2.err?.message}`);
  const d = await essai('lent', { source });
  ok('D. génération lente mais active : rendue, jamais coupée', d.ok && d.texte === 'Bonjour', `${d.s}s ${d.err?.message}`);
  const d2 = await essai('done-ouvert', { source });
  ok('D. [DONE] puis connexion laissée ouverte : rendu tout de suite (pas au bout du silence)',
     d2.ok && d2.texte === 'Bonjour' && d2.s < a.s + 1.5 && d2.journal.usage === 1, `${d2.s}s (normal ${a.s}s) ${d2.err?.message}`);
  const tr = await essai('tronque', { source });
  ok('D. flux fermé AVANT la fin (réponse tronquée) : erreur fournisseur, jamais facturée',
     !tr.ok && tr.err.fournisseur && /interrupted before the end/.test(tr.err.message) && tr.journal.usage === 0, `${tr.err?.message} usage=${tr.journal.usage}`);
  const e = await essai('coupure', { source });
  ok('E. génération coupée : erreur fournisseur « generation stopped »', !e.ok && e.err.fournisseur && /generation stopped/.test(e.err.message), `${e.err?.message}`);
  const f = await essai('429', { source });
  ok('F. 429 répété : erreur fournisseur après 1 retry', !f.ok && f.err.fournisseur && f.journal.fetchs === 2, `${f.journal.fetchs} fetch · ${f.err?.message}`);
  // G — fast-fail dans le même contexte que B
  const t0 = Date.now(); const avant = b.journal.fetchs;
  let g = null; try { await b.ctx.callAIText('[1] x'); } catch (err) { g = err; }
  ok('G. fast-fail : l’appel suivant échoue en < 50 ms, sans fetch', g && g.fournisseur && Date.now() - t0 < 50 && b.journal.fetchs === avant, `${Date.now() - t0} ms`);
  const h1 = await essai('gemini-muet', { source, moteur: 'gemini' });
  ok('H. Gemini muet : erreur fournisseur au délai total', !h1.ok && h1.err.fournisseur && h1.s < 6, `${h1.s}s ${h1.err?.message}`);
  const h2 = await essai('gemini-ok', { source, moteur: 'gemini' });
  ok('H. Gemini normal : texte + usage', h2.ok && h2.texte === 'Bonjour' && h2.journal.usage === 1, `${h2.err?.message}`);
  return R;
}

const resultats = await scenario();
const motif = "if (!l || l.charAt(0) === ':' || l.indexOf('data:') !== 0) continue;";
if (SOURCE.includes(motif)) {
  const sabote = SOURCE.replace(motif, "if (!l) continue; if (l.charAt(0) === ':') { dernier = Date.now(); continue; } if (l.indexOf('data:') !== 0) continue;");
  const rouges = (await scenario(sabote)).filter(([, c]) => !c).map(([n]) => n);
  resultats.push(['I. mutation détectée : keep-alive compté comme une réponse', rouges.length > 0, rouges.join(' | ')]);
} else {
  resultats.push(['I. mutation applicable', false, 'motif introuvable']);
}
for (const [nom, cond, det] of resultats) console.log(`  ${cond ? 'OK   ' : 'ECHEC'} ${nom}${!cond && det ? '  — ' + det : ''}`);
const bons = resultats.filter(([, c]) => c).length;
console.log(`VERDICT : ${bons}/${resultats.length}`);
process.exit(bons === resultats.length ? 0 : 1);

/* ==========================================================================
   Planning des agents : expressions cron (fuseau UTC) déclarées par chaque
   agent dans son journal (data/journal/*.json, champ `planning`).
   Sans dépendance au DOM : testé sous Node (js/tests/planning.test.mjs).

   Statut lié au planning, à l'instant `maintenant` :
   - « manquante » : première exécution prévue après la dernière exécution
     réussie, déjà passée (null si aucune n'est passée) ;
   - « en retard »  : elle manque depuis plus de 45 min (agent infra-horaire)
                      ou 2 h (agent quotidien) ;
   - « en panne »   : elle manque depuis plus de 2 h (agent infra-horaire)
                      ou 26 h (agent quotidien) ;
   - « en pause »   : rien ne manque et l'on est dans une longue plage sans
                      exécution prévue (nuit) : écart entre la dernière exécution
                      prévue et la suivante supérieur au seuil de panne.
   ========================================================================== */

const MINUTE = 60_000;
const HUIT_JOURS = 8 * 24 * 60;

/** Seuils (en minutes) selon l'intervalle de base de l'agent. */
export function seuils(intervalleBase) {
  if (intervalleBase != null && intervalleBase <= 60) return { retard: 45, panne: 120 };
  return { retard: 120, panne: 26 * 60 };
}

function champ(expr, mini, maxi) {
  const valeurs = new Set();
  for (let morceau of expr.split(',')) {
    let pas = 1;
    if (morceau.includes('/')) {
      const [m, p] = morceau.split('/');
      morceau = m;
      pas = Number(p);
    }
    let debut;
    let fin;
    if (morceau === '*') {
      debut = mini; fin = maxi;
    } else if (morceau.includes('-')) {
      [debut, fin] = morceau.split('-').map(Number);
    } else {
      debut = Number(morceau);
      fin = pas > 1 ? maxi : debut;
    }
    for (let v = debut; v <= fin; v += pas) valeurs.add(v);
  }
  return valeurs;
}

/** Compile une expression cron (5 champs, UTC) en fonction de test. */
export function compilerCron(expr) {
  const [mi, h, j, mo, js] = expr.trim().split(/\s+/);
  const minutes = champ(mi, 0, 59);
  const heures = champ(h, 0, 23);
  const jours = champ(j, 1, 31);
  const mois = champ(mo, 1, 12);
  const joursSem = new Set([...champ(js, 0, 7)].map((v) => (v === 7 ? 0 : v)));
  return (d) => minutes.has(d.getUTCMinutes()) && heures.has(d.getUTCHours())
    && jours.has(d.getUTCDate()) && mois.has(d.getUTCMonth() + 1) && joursSem.has(d.getUTCDay());
}

function compiler(crons) {
  const tests = crons.map(compilerCron);
  return (d) => tests.some((t) => t(d));
}

const aLaMinute = (t) => Math.floor(t / MINUTE) * MINUTE;

/** Dernière minute planifiée (ms) à ou avant `t`, dans les 8 jours ; sinon null. */
export function precedente(crons, t) {
  const test = compiler(crons);
  let m = aLaMinute(t);
  for (let i = 0; i < HUIT_JOURS; i += 1, m -= MINUTE) if (test(new Date(m))) return m;
  return null;
}

/** Première minute planifiée (ms) strictement après `t`, dans les 8 jours ; sinon null. */
export function suivante(crons, t) {
  const test = compiler(crons);
  let m = aLaMinute(t) + MINUTE;
  for (let i = 0; i < HUIT_JOURS; i += 1, m += MINUTE) if (test(new Date(m))) return m;
  return null;
}

/** Plus petit écart (min) entre deux exécutions planifiées sur une semaine (15 pour l'agent marchés). */
export function intervalleBase(crons, depuis = Date.UTC(2026, 0, 5)) {
  const test = compiler(crons);
  let precedenteMin = null;
  let mini = null;
  for (let i = 0; i < 7 * 24 * 60 + 1; i += 1) {
    if (test(new Date(depuis + i * MINUTE))) {
      if (precedenteMin != null && (mini == null || i - precedenteMin < mini)) mini = i - precedenteMin;
      precedenteMin = i;
    }
  }
  return mini ?? (precedenteMin != null ? 7 * 24 * 60 : null);
}

/**
 * Situation d'un agent vis-à-vis de son planning.
 * `sante` : { derniere_execution, prochaine_prevue, intervalle_min, planning: { crons, fuseau } }.
 * Renvoie { etat: 'ok' | 'pause' | 'retard' | 'panne', manquante, retardMin, prochaine, seuils, base }.
 */
export function situationPlanning(sante, maintenant = Date.now()) {
  const derniere = Date.parse(sante?.derniere_execution ?? '');
  if (Number.isNaN(derniere)) return { etat: 'panne', manquante: null, retardMin: null, prochaine: null, seuils: seuils(null), base: null };
  const crons = sante.planning?.crons?.length ? sante.planning.crons : null;
  let manquante;
  let prochaine;
  let base;
  let ecartPlage;
  if (crons) {
    base = intervalleBase(crons);
    manquante = suivante(crons, derniere);
    prochaine = suivante(crons, maintenant);
    const derniereprevue = precedente(crons, maintenant);
    ecartPlage = prochaine != null && derniereprevue != null ? (prochaine - derniereprevue) / MINUTE : null;
  } else {
    // Ancien journal sans planning : on se fie à la prochaine exécution annoncée par l'agent
    base = sante.intervalle_min ?? null;
    manquante = Date.parse(sante.prochaine_prevue ?? '');
    if (Number.isNaN(manquante)) manquante = base ? derniere + base * MINUTE : null;
    prochaine = manquante != null && manquante > maintenant ? manquante : null;
    ecartPlage = manquante != null ? (manquante - derniere) / MINUTE : null;
  }
  const s = seuils(base);
  if (manquante != null && manquante <= maintenant) {
    const retardMin = (maintenant - manquante) / MINUTE;
    const etat = retardMin > s.panne ? 'panne' : retardMin > s.retard ? 'retard' : 'ok';
    return { etat, manquante, retardMin, prochaine, seuils: s, base };
  }
  const etat = ecartPlage != null && ecartPlage > s.panne ? 'pause' : 'ok';
  return { etat, manquante: null, retardMin: 0, prochaine, seuils: s, base };
}

/** « lun. 8 h 07 » en heure de Paris. */
export function heureParis(t) {
  const d = new Date(t);
  const jour = d.toLocaleDateString('fr-FR', { weekday: 'short', timeZone: 'Europe/Paris' });
  const parties = Object.fromEntries(new Intl.DateTimeFormat('fr-FR', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Europe/Paris' })
    .formatToParts(d).map((p) => [p.type, p.value]));
  return `${jour} ${Number(parties.hour)} h ${parties.minute}`;
}

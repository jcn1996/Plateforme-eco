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
const JOUR = 24 * 60 * MINUTE;
const HORIZON = 35 * JOUR; // assez pour un planning mensuel (backtest) ; les jours sans exécution prévue sont sautés

/** Seuils (en minutes) selon l'intervalle de base de l'agent. */
export function seuils(intervalleBase) {
  if (intervalleBase != null && intervalleBase <= 60) return { retard: 45, panne: 120 };
  // Agent mensuel (backtest) : exécution de plusieurs heures, relancée par le planificateur en cas d'échec
  if (intervalleBase != null && intervalleBase > 8 * 24 * 60) return { retard: 8 * 60, panne: 48 * 60 };
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

/** Compile une expression cron (5 champs, UTC) en fonction de test ; `.jour(d)` teste seulement le jour. */
export function compilerCron(expr) {
  const [mi, h, j, mo, js] = expr.trim().split(/\s+/);
  const minutes = champ(mi, 0, 59);
  const heures = champ(h, 0, 23);
  const jours = champ(j, 1, 31);
  const mois = champ(mo, 1, 12);
  const joursSem = new Set([...champ(js, 0, 7)].map((v) => (v === 7 ? 0 : v)));
  const jour = (d) => jours.has(d.getUTCDate()) && mois.has(d.getUTCMonth() + 1) && joursSem.has(d.getUTCDay());
  const test = (d) => minutes.has(d.getUTCMinutes()) && heures.has(d.getUTCHours()) && jour(d);
  test.jour = jour;
  return test;
}

function compiler(crons) {
  const tests = crons.map(compilerCron);
  const test = (d) => tests.some((t) => t(d));
  test.jour = (d) => tests.some((t) => t.jour(d));
  return test;
}

const aLaMinute = (t) => Math.floor(t / MINUTE) * MINUTE;
const debutDuJour = (t) => Math.floor(t / JOUR) * JOUR;

/** Dernière minute planifiée (ms) à ou avant `t`, dans les 35 jours ; sinon null. */
export function precedente(crons, t) {
  const test = compiler(crons);
  const limite = aLaMinute(t) - HORIZON;
  for (let m = aLaMinute(t); m >= limite;) {
    const d = new Date(m);
    if (!test.jour(d)) { m = debutDuJour(m) - MINUTE; continue; } // aucun créneau ce jour-là : fin de la veille
    if (test(d)) return m;
    m -= MINUTE;
  }
  return null;
}

/** Première minute planifiée (ms) strictement après `t`, dans les 35 jours ; sinon null. */
export function suivante(crons, t) {
  const test = compiler(crons);
  const limite = aLaMinute(t) + HORIZON;
  for (let m = aLaMinute(t) + MINUTE; m <= limite;) {
    const d = new Date(m);
    if (!test.jour(d)) { m = debutDuJour(m) + JOUR; continue; } // aucun créneau ce jour-là : début du lendemain
    if (test(d)) return m;
    m += MINUTE;
  }
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
  if (mini != null) return mini;
  if (precedenteMin != null) return 7 * 24 * 60;
  // Aucune exécution dans la semaine type : planning mensuel, intervalle mesuré entre deux créneaux successifs
  const a = suivante(crons, depuis);
  const b = a != null ? suivante(crons, a) : null;
  return a != null && b != null ? (b - a) / MINUTE : null;
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

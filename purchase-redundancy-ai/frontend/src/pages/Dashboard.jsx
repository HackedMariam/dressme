import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api, asset, errorMessage } from '../api';
import { track } from '../utils/analytics';
import Icon from '../components/Icon';
import { HBars, Kpi, Legend, StackedColumns, SystemHealth, VERDICT_SERIES, VerdictTable, fillDays } from '../components/charts';
import { ColorDot, Empty, ItemCard, ScoreRing } from '../components/ui';
import Proposal from '../components/Proposal';
import { categoryLabel, formatPrice, genderLabel } from '../labels';

const RANGES = [{ days: 7, label: '7 j' }, { days: 30, label: '30 j' }, { days: 90, label: '90 j' }];
const SCORES = [
  { key: 'balance', label: 'Équilibre', hint: 'composition proche de l’idéal' },
  { key: 'uniqueness', label: 'Sans doublon', hint: 'peu de pièces en double' },
  { key: 'versatility', label: 'Polyvalence', hint: 'tenues harmonieuses possibles' },
  { key: 'harmony', label: 'Couleurs', hint: 'harmonie de la palette' },
];
const SEVERITY = { high: { label: 'Prioritaire', tone: 'bad' }, medium: { label: 'Conseillé', tone: 'warn' }, low: { label: 'Bonus', tone: 'good' } };
const STATUS = { low: 'Manque', ok: 'Équilibré', high: 'Trop' };
const PAGE_NAMES = { home: 'Accueil', scan: 'Dois-je l’acheter ?', agent: 'Styliste IA', wardrobe: 'Garde-robe', catalog: 'Trouver similaire', stats: 'Tableau de bord', studio: 'Studio', profile: 'Profil de style' };
const SOURCE_NAMES = { openai: 'GPT', claude: 'Claude', rules: 'Règles locales' };

const healthTone = (v) => (v >= 75 ? 'good' : v >= 50 ? 'warn' : 'bad');

export default function Dashboard({ notify, liveTick, user, wardrobe, refreshWardrobe, refreshStatus, refreshActions, openStarter, openCatalog, go }) {
  const [report, setReport] = useState(null);
  const [activity, setActivity] = useState(null);
  const [system, setSystem] = useState(null);
  const [days, setDays] = useState(30);
  const [asTable, setAsTable] = useState(false);
  const [allDuplicates, setAllDuplicates] = useState(false);
  const [daily, setDaily] = useState(null);
  const [actions, setActions] = useState([]);

  const loadActions = useCallback(() => api.get('/agent/actions', { params: { status: 'pending' } })
    .then((r) => setActions(r.data.items)).catch(() => setActions([])), []);
  useEffect(() => { loadActions(); }, [loadActions, liveTick, wardrobe.length]);
  useEffect(() => {
    if (!wardrobe.length) { setDaily(null); return; }
    api.get('/outfits/daily').then((r) => setDaily(r.data)).catch(() => setDaily(null));
  }, [wardrobe.length, user?.id]);

  const loadReport = useCallback(() => api.get('/insights').then((r) => setReport(r.data))
    .catch((e) => notify(errorMessage(e), 'bad')), [notify]);
  useEffect(() => { loadReport(); }, [loadReport, liveTick, user?.id, wardrobe.length]);
  useEffect(() => {
    api.get('/analytics/summary', { params: { days } }).then((r) => setActivity(r.data)).catch(() => setActivity(null));
  }, [days, liveTick, user?.id]);

  const timeline = useMemo(() => fillDays(activity?.timeline || [], days), [activity, days]);

  const remove = async (piece) => {
    if (!window.confirm(`Retirer « ${piece.name} » de votre garde-robe ?`)) return;
    try {
      await api.delete(`/wardrobe/${piece.id}`);
      track('duplicate_removed', 'stats');
      notify(`« ${piece.name} » retiré`, 'good');
      await Promise.all([refreshWardrobe(), refreshStatus()]);
    } catch (e) {
      notify(errorMessage(e), 'bad');
    }
  };

  const runAction = (action) => {
    if (!action) return;
    if (action.type === 'starter') openStarter();
    else if (action.type === 'catalog') openCatalog({ category: action.category, color: action.color });
    else document.getElementById(`section-${action.type}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  if (!report) return <div className="page"><div className="center"><span className="spinner" /></div></div>;

  return (
    <div className="page dashboard">
      <header className="page-head greeting">
        <div>
          <h2>{greeting()}, {user ? (user.display_name || user.email).split(' ')[0] : 'bienvenue'}.</h2>
          <p>{new Date().toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'long' })} · {user ? genderLabel(user.gender) : 'Garde-robe invitée'} · {wardrobe.length} pièces</p>
        </div>
        <button className="btn btn-ghost" onClick={() => go('agent')}><Icon name="agent" /> Demander au styliste</button>
      </header>

      {daily?.outfit && <DailyLook daily={daily} go={go} />}

      {actions.length > 0 && (
        <section className="card">
          <h3>L’agent attend votre accord</h3>
          <p className="muted small" style={{ marginBottom: 12 }}>Ce que le styliste a repéré ou préparé pour vous. Rien n’est modifié sans votre approbation.</p>
          <div className="actions-list">
            {actions.map((a) => (
              <Proposal key={a.id} action={a} notify={notify}
                onDecided={() => { loadActions(); refreshActions?.(); refreshWardrobe(); refreshStatus(); }} />
            ))}
          </div>
        </section>
      )}

      {report.empty ? (
        <Empty icon="hanger" title="Votre garde-robe est vide">
          <p>Ajoutez vos pièces pour obtenir un diagnostic.</p>
          <button className="btn btn-primary" onClick={openStarter}><Icon name="sparkle" /> Garde-robe de départ</button>
        </Empty>
      ) : (
        <>
          <section className="card health-card">
            <ScoreRing value={report.health} tone={healthTone(report.health)} size={128} label="santé" />
            <div className="health-main">
              <h3>Santé de votre garde-robe</h3>
              <p className="muted">
                {report.pieces} pièces · {report.outfits.good_outfits} tenues harmonieuses possibles
                {report.extra_pieces > 0 && <> · <strong className="danger-text">{report.extra_pieces} pièce{report.extra_pieces > 1 ? 's' : ''} en double</strong></>}
                {report.value > 0 && <> · valeur {formatPrice(report.value)}</>}
              </p>
              <div className="subscores">
                {SCORES.map((s) => (
                  <div key={s.key} className="subscore" title={s.hint}>
                    <span>{s.label}</span>
                    <div className="meter"><div className={`meter-fill tone-${healthTone(report.scores[s.key])}`} style={{ width: `${report.scores[s.key]}%` }} /></div>
                    <b>{report.scores[s.key]}</b>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section className="card">
            <h3>Mes conseils</h3>
            <ul className="tips">
              {report.tips.map((tip) => (
                <li key={tip.id} className={`tip-row tone-${SEVERITY[tip.severity].tone}`}>
                  <span className={`severity sev-${tip.severity}`}>{SEVERITY[tip.severity].label}</span>
                  <div>
                    <strong>{tip.title}</strong>
                    <p>{tip.detail}</p>
                  </div>
                  {tip.action && (
                    <button className="btn btn-ghost btn-sm" onClick={() => runAction(tip.action)}>
                      {{ starter: 'Compléter', catalog: 'Voir le catalogue', duplicates: 'Voir', orphans: 'Voir' }[tip.action.type]}
                      <Icon name="arrow" size={14} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </section>

          <div className="dash-grid">
            <section className="card">
              <h3>Composition</h3>
              <p className="muted small">Vos pièces par catégorie, comparées à une garde-robe équilibrée
                {user?.gender && user.gender !== 'Unspecified' ? ` ${user.gender === 'Women' ? 'féminine' : 'masculine'}` : ''} de même taille.</p>
              <ul className="compo">
                {report.composition.map((row) => {
                  const max = Math.max(...report.composition.map((r) => Math.max(r.have, r.ideal)), 1);
                  return (
                    <li key={row.category}>
                      <span className="compo-label">{categoryLabel(row.category)}</span>
                      <span className="compo-track" title={`${row.have} pièces, ${row.ideal} conseillées`}>
                        <span className={`compo-fill st-${row.status}`} style={{ width: `${(row.have / max) * 100}%` }} />
                        <span className="compo-ideal" style={{ left: `${(row.ideal / max) * 100}%` }} />
                      </span>
                      <span className="compo-value">{row.have}<small>/{row.ideal}</small></span>
                      <span className={`compo-status st-${row.status}`}>{STATUS[row.status]}</span>
                    </li>
                  );
                })}
              </ul>
              <p className="muted small legend-note"><span className="compo-ideal-key" /> quantité conseillée</p>
            </section>

            <section className="card">
              <h3>Palette</h3>
              <p className="muted small">{Math.round(report.palette.neutral_share * 100)} % de couleurs neutres · harmonie {report.scores.harmony}/100</p>
              <div className="palette">
                {report.palette.colors.slice(0, 10).map((c) => (
                  <div key={c.color} className="palette-row" title={`${c.count} pièce(s)`}>
                    <ColorDot color={c.color} />
                    <span>{c.label}</span>
                    <div className="meter"><div className="meter-fill" style={{ width: `${c.share * 100}%` }} /></div>
                    <b>{Math.round(c.share * 100)} %</b>
                  </div>
                ))}
              </div>
            </section>
          </div>

          <section className="card" id="section-duplicates">
            <h3>Doublons {report.duplicates.length > 0 && <span className="tag">{report.duplicates.length} groupe{report.duplicates.length > 1 ? 's' : ''}</span>}</h3>
            {report.duplicates.length === 0 ? (
              <p className="muted">Aucune pièce en double. Bravo !</p>
            ) : (
              <>
                <p className="muted small">Pièces quasi identiques (vision CLIP). Gardez la plus polyvalente ; revendez ou donnez les autres.</p>
                <div className="dup-groups">
                  {(allDuplicates ? report.duplicates : report.duplicates.slice(0, 3)).map((group) => (
                    <div key={group.keep} className="dup-group">
                      {group.items.map((piece) => (
                        <figure key={piece.id} className={piece.id === group.keep ? 'keep' : 'extra'}>
                          <img src={asset(piece.image_url)} alt={piece.name} />
                          <figcaption>
                            <span>{piece.name}</span>
                            {piece.id === group.keep
                              ? <em className="keep-badge">À garder</em>
                              : <button className="btn btn-ghost btn-sm" onClick={() => remove(piece)}><Icon name="trash" size={14} /> Retirer</button>}
                          </figcaption>
                        </figure>
                      ))}
                      <span className="dup-sim">{Math.round(group.similarity * 100)} % similaires</span>
                    </div>
                  ))}
                </div>
                {report.duplicates.length > 3 && (
                  <button className="btn btn-ghost btn-sm show-more" onClick={() => setAllDuplicates((v) => !v)}>
                    {allDuplicates ? 'Réduire' : `Voir les ${report.duplicates.length - 3} autres groupes`}
                  </button>
                )}
              </>
            )}
          </section>

          <div className="dash-grid" id="section-orphans">
            <section className="card">
              <h3>Pièces stars</h3>
              <p className="muted small">Celles qui entrent dans le plus de tenues harmonieuses.</p>
              <div className="thumb-row">
                {report.outfits.stars.map((p) => (
                  <figure key={p.id} className="thumb"><img src={asset(p.image_url)} alt={p.name} /><figcaption>{p.outfits} tenues</figcaption></figure>
                ))}
              </div>
            </section>
            <section className="card">
              <h3>Pièces orphelines</h3>
              <p className="muted small">Elles ne forment aucune tenue harmonieuse avec le reste.</p>
              {report.outfits.orphans.length === 0 ? <p className="muted">Aucune : tout s’associe.</p> : (
                <div className="thumb-row">
                  {report.outfits.orphans.map((p) => (
                    <figure key={p.id} className="thumb"><img src={asset(p.image_url)} alt={p.name} /><figcaption>{p.name}</figcaption></figure>
                  ))}
                </div>
              )}
            </section>
          </div>

          {report.suggestions.length > 0 && (
            <section className="card">
              <h3>Achats vraiment utiles</h3>
              <p className="muted small">Des produits réels qui comblent vos manques{user?.gender && user.gender !== 'Unspecified' ? `, ${user.gender === 'Women' ? 'pour femme' : 'pour homme'}` : ''}.</p>
              <div className="card-grid">
                {report.suggestions.map((p) => (
                  <ItemCard key={p.id} item={p} compact><p className="tip">{p.reason}</p></ItemCard>
                ))}
              </div>
            </section>
          )}
        </>
      )}

      {activity && (
        <section className="card chart-card">
          <div className="chart-head">
            <div>
              <h3>Mon activité</h3>
              <p className="muted small">Achats analysés avant de passer en caisse</p>
            </div>
            <div className="segmented" role="tablist" aria-label="Période">
              {RANGES.map((r) => (
                <button key={r.days} role="tab" aria-selected={days === r.days} className={days === r.days ? 'active' : ''}
                  onClick={() => setDays(r.days)}>{r.label}</button>
              ))}
            </div>
          </div>
          <div className="kpi-row compact">
            <Kpi label="Articles analysés" value={activity.analyses} />
            <Kpi label="Doublons évités" value={activity.verdicts.skip || 0} />
            <Kpi label="Argent économisé" value={formatPrice(activity.money_saved)} />
            <Kpi label="Score moyen" value={activity.average_score ?? '—'} hint="redondance sur 100" />
          </div>
          {activity.analyses === 0 ? (
            <p className="muted">Aucune analyse sur la période — scannez un article avant de l’acheter.</p>
          ) : (
            <>
              <div className="chart-head">
                <Legend series={VERDICT_SERIES} />
                <button className="btn btn-ghost btn-sm" onClick={() => setAsTable((v) => !v)}>{asTable ? 'Graphique' : 'Tableau'}</button>
              </div>
              {asTable ? <VerdictTable rows={timeline.filter((d) => d.total)} /> : <StackedColumns rows={timeline} series={VERDICT_SERIES} />}
            </>
          )}
        </section>
      )}

      <details className="card tech-details" onToggle={(e) => e.target.open && !system &&
        api.get('/analytics/system').then((r) => setSystem(r.data)).catch(() => {})}>
        <summary><Icon name="chart" size={16} /> Données techniques (développeurs)</summary>
        {system && <SystemHealth system={system} />}
        {activity && (
          <div className="dash-grid">
            <div><h4>Pages consultées</h4><HBars data={Object.entries(activity.page_views).map(([k, v]) => [PAGE_NAMES[k] || k, v])} unit="visite" /></div>
            <div><h4>Explications rédigées par</h4><HBars data={Object.entries(activity.explanation_sources).map(([k, v]) => [SOURCE_NAMES[k] || k, v])} unit="explication" /></div>
          </div>
        )}
        {report.computed_ms !== undefined && <p className="muted small">Diagnostic calculé en {report.computed_ms} ms.</p>}
      </details>
    </div>
  );
}

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? 'Bonsoir' : h < 18 ? 'Bonjour' : 'Bonsoir';
}

/** The agent's look of the day - a real outfit from the wardrobe, scored by the engine */
function DailyLook({ daily, go }) {
  const pieces = daily.outfit.pieces;
  const SEASON = { winter: 'd’hiver', summer: 'd’été', spring: 'de printemps', fall: 'd’automne' };
  return (
    <section className="night daily">
      <div className="daily-main">
        <div>
          <span className="night-eyebrow">Recommandation IA du jour</span>
          <h3>La tenue {SEASON[daily.season] || 'du jour'}</h3>
          <p>{daily.feedback?.[0]}</p>
        </div>
        <div className="daily-pieces">
          {pieces.map((p) => (
            <div key={p.id} className="daily-piece"><small>{categoryLabel(p.category)}</small><span>{p.name}</span></div>
          ))}
        </div>
        <div className="daily-score">
          <ScoreRing value={daily.outfit.score} size={64} label="" />
          <div>
            <strong>Score de synergie</strong>
            <small>{daily.why.join(' · ')}</small>
          </div>
          <button className="btn btn-primary btn-sm" onClick={() => go('studio')} style={{ marginLeft: 'auto' }}>Ouvrir le studio</button>
        </div>
      </div>
      <div className="daily-visual">
        {pieces.slice(0, 4).map((p) => <img key={p.id} src={asset(p.image_url)} alt={p.name} />)}
      </div>
    </section>
  );
}

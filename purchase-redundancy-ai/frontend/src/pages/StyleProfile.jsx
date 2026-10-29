import React, { useEffect, useState } from 'react';
import { api } from '../api';
import Icon from '../components/Icon';
import { Empty } from '../components/ui';
import { COLORS, genderLabel, styleLabel } from '../labels';

const hexOf = (value) => COLORS.find((c) => c.value === value)?.hex || '#c9c7bf';

/** "Archétype" from the wardrobe itself: dominant style and the share of neutral colors */
function archetype(report) {
  const dominant = report.style?.dominant;
  const neutral = report.palette?.neutral_share ?? 0;
  if (neutral >= 0.75) return { name: 'Minimaliste intemporel', text: 'Une base presque entièrement neutre : tout s’associe, peu de risques de doublons de couleur.' };
  if (neutral < 0.4) return { name: 'Coloriste', text: 'Vos couleurs vives font votre signature ; quelques basiques neutres multiplieraient les tenues.' };
  if (dominant === 'formal' || dominant === 'classic') return { name: 'Classique raffiné', text: 'Des pièces structurées et sobres, pensées pour durer.' };
  if (dominant === 'sporty') return { name: 'Sportif urbain', text: 'Confort et mouvement d’abord, avec une base neutre.' };
  return { name: 'Décontracté équilibré', text: 'Des pièces faciles à porter au quotidien, sur une base neutre.' };
}

export default function StyleProfile({ user, wardrobe, liveTick, openProfile, openAccount, openStarter }) {
  const [report, setReport] = useState(null);
  useEffect(() => {
    api.get('/insights').then((r) => setReport(r.data)).catch(() => setReport(null));
  }, [liveTick, wardrobe.length, user?.id]);

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Profil de style</h2>
          <p>Vos goûts, vos tailles et l’empreinte de votre garde-robe — calculés sur vos {wardrobe.length} pièces.</p>
        </div>
        {user
          ? <button className="btn btn-primary" onClick={openProfile}><Icon name="user" size={16} /> Modifier le profil</button>
          : <button className="btn btn-primary" onClick={openAccount}><Icon name="user" size={16} /> Créer mon profil</button>}
      </header>

      {!report || report.empty ? (
        <Empty icon="hanger" title="Pas encore assez de pièces">
          <p>Votre profil se calcule à partir de votre garde-robe.</p>
          <button className="btn btn-primary" onClick={openStarter}><Icon name="sparkle" /> Garde-robe de départ</button>
        </Empty>
      ) : (
        <ProfileBody report={report} user={user} />
      )}
    </div>
  );
}

function ProfileBody({ report, user }) {
  const distribution = Object.entries(report.style?.distribution || {}).sort((a, b) => b[1] - a[1]);
  const total = distribution.reduce((n, [, v]) => n + v, 0) || 1;
  const type = archetype(report);
  const favorites = user?.favorite_colors || [];

  return (
    <div className="profile-grid">
      <div className="studio-main">
        <section className="card">
          <h3>Esthétique de votre garde-robe</h3>
          <p className="muted small" style={{ marginBottom: 16 }}>Part de chaque style parmi vos pièces · cohérence {Math.round((report.style?.consistency ?? 0) * 100)} %</p>
          {distribution.map(([style, n]) => (
            <div key={style} className="aesthetic">
              <div className="aesthetic-head"><span>{styleLabel(style)}</span><span>{Math.round((n / total) * 100)} %</span></div>
              <div className="track"><div style={{ width: `${(n / total) * 100}%` }} /></div>
            </div>
          ))}
        </section>

        <div className="dash-grid">
          <section className="card">
            <h3>Votre palette</h3>
            <p className="muted small" style={{ marginBottom: 14 }}>{Math.round(report.palette.neutral_share * 100)} % de neutres · harmonie {report.scores.harmony}/100</p>
            <div className="swatches">
              {report.palette.colors.slice(0, 8).map((c) => (
                <div key={c.color} className="swatch-big"><span style={{ background: hexOf(c.color) }} />{c.label} · {Math.round(c.share * 100)} %</div>
              ))}
            </div>
          </section>
          <section className="card">
            <h3>Couleurs préférées</h3>
            {favorites.length ? (
              <div className="swatches" style={{ marginTop: 10 }}>
                {favorites.map((c) => <div key={c} className="swatch-big"><span style={{ background: hexOf(c) }} />{COLORS.find((x) => x.value === c)?.label || c}</div>)}
              </div>
            ) : <p className="muted small">Indiquez-les dans votre profil : la garde-robe de départ et les suggestions s’y adaptent.</p>}
            {user?.style_preferences?.length > 0 && (
              <p className="small" style={{ marginTop: 14 }}>Styles choisis : {user.style_preferences.map(styleLabel).join(', ')}</p>
            )}
          </section>
        </div>
      </div>

      <aside className="studio-main">
        <section className="night archetype">
          <span className="night-eyebrow">Votre archétype</span>
          <strong>{type.name}</strong>
          <p>{type.text}</p>
        </section>
        <section className="card">
          <span className="eyebrow-label">Mesures</span>
          <dl className="kv" style={{ marginTop: 8 }}>
            <div><dt>Profil</dt><dd>{genderLabel(user?.gender)}</dd></div>
            <div><dt>Vêtements</dt><dd>{user?.clothing_size || '—'}</dd></div>
            <div><dt>Pointure</dt><dd>{user?.shoe_size ? `EU ${user.shoe_size}` : '—'}</dd></div>
          </dl>
        </section>
        <section className="card">
          <span className="eyebrow-label">Garde-robe</span>
          <dl className="kv" style={{ marginTop: 8 }}>
            <div><dt>Pièces</dt><dd>{report.pieces}</dd></div>
            <div><dt>Santé</dt><dd>{report.health}/100</dd></div>
            <div><dt>Tenues possibles</dt><dd>{report.outfits.good_outfits}</dd></div>
            <div><dt>Pièces en double</dt><dd>{report.extra_pieces}</dd></div>
          </dl>
        </section>
      </aside>
    </div>
  );
}

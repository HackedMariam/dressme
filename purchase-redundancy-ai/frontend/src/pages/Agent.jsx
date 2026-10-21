import React, { useEffect, useRef, useState } from 'react';
import { asset, errorMessage, resizeImage, streamAgent } from '../api';
import { track } from '../utils/analytics';
import Icon from '../components/Icon';
import CameraModal from '../components/CameraModal';
import { ItemCard, ScoreRing, VerdictPill } from '../components/ui';
import { VERDICTS, llmName } from '../labels';

// Missions the advisor knows - each starts a conversation turn with a ready-made question
const SHORTCUTS = [
  { mission: 'audit', icon: 'chart', title: 'Diagnostic', text: 'Fais le diagnostic de ma garde-robe.' },
  { mission: 'outfits', icon: 'hanger', title: 'Que porter ?', text: 'Que porter pour un entretien cette semaine ?' },
  { mission: 'shopping', icon: 'wallet', title: 'Quoi acheter ?', text: 'Que me manque-t-il vraiment ? J’ai 150 $.' },
  { mission: 'declutter', icon: 'trash', title: 'Trier & revendre', text: 'Quelles pièces devrais-je revendre ou donner ?' },
  { mission: 'ask', icon: 'scan', title: 'Dois-je l’acheter ?', text: 'Je pense acheter des baskets blanches en cuir à 120 $.' },
];
const STORE_KEY = 'doublon.advisor';
const MODE_NAMES = { claude: 'Claude', openai: 'GPT', local: 'agent local' };

function loadTurns() {
  try { return JSON.parse(sessionStorage.getItem(STORE_KEY)) || []; } catch { return []; }
}

/** Text the LLM sees for an earlier assistant turn (answer, or headline + reasons) */
function turnText(turn) {
  const f = turn.final;
  if (!f) return turn.error || '(pas de réponse)';
  return (f.answer || [f.headline, ...(f.reasons || [])].join('\n')).slice(0, 3900);
}

export default function Agent({ wardrobe, health, refreshStatus, addToWardrobe, go, user, openStarter }) {
  const [turns, setTurns] = useState(loadTurns);   // [{ id, question, photo, mission, run: {...}, final, error }]
  const [text, setText] = useState('');
  const [photo, setPhoto] = useState(null);
  const [camera, setCamera] = useState(false);
  const [running, setRunning] = useState(false);
  const abortRef = useRef(null);
  const endRef = useRef(null);
  const fileRef = useRef(null);

  useEffect(() => {
    try { sessionStorage.setItem(STORE_KEY, JSON.stringify(turns.map((t) => ({ ...t, photo: null })))); } catch { /* full */ }
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [turns]);

  const send = async (question, mission = 'ask') => {
    if (running || (!question.trim() && !photo)) return;
    const id = Date.now();
    const history = turns.filter((t) => t.final || t.error).slice(-5).flatMap((t) => [
      { role: 'user', content: t.question || 'Photo' }, { role: 'assistant', content: turnText(t) }]);
    const image = photo;
    setTurns((all) => [...all, { id, question, photo: image, mission, plan: [], steps: {}, order: [], final: null, error: null }]);
    setText('');
    setPhoto(null);
    setRunning(true);
    const controller = new AbortController();
    abortRef.current = controller;
    const update = (fn) => setTurns((all) => all.map((t) => (t.id === id ? fn(t) : t)));

    const onEvent = (event) => update((t) => {
      if (event.type === 'start') return { ...t, mode: event.mode, plan: event.plan, mission: event.mission };
      if (event.type === 'step') {
        const order = t.order.includes(event.id) ? t.order : [...t.order, event.id];
        return { ...t, order, steps: { ...t.steps, [event.id]: { ...t.steps[event.id], ...event } } };
      }
      if (event.type === 'final') return { ...t, final: event };
      if (event.type === 'error') return { ...t, error: event.message };
      if (event.type === 'notice') return { ...t, notice: event.message };
      return t;
    });

    try {
      track('agent_run', 'agent', { mission, with_photo: Boolean(image), turn: history.length / 2 + 1 });
      await streamAgent({ mission, message: question, image_base64: image, history }, onEvent, controller.signal);
    } catch (e) {
      if (e.name !== 'AbortError') update((t) => ({ ...t, error: errorMessage(e) }));
    } finally {
      setRunning(false);
      refreshStatus();
    }
  };

  const pickFile = async (e) => {
    const file = e.target.files?.[0];
    if (file) setPhoto(await resizeImage(file));
    e.target.value = '';
  };

  const llmOn = health?.llm?.available;
  const empty = turns.length === 0;

  return (
    <div className="page advisor">
      <header className="page-head">
        <div>
          <h2>Conseiller IA</h2>
          <p>Posez vos questions : il analyse votre garde-robe, compose vos tenues et vous dit quoi acheter — ou pas.</p>
        </div>
        <div className="head-actions">
          <span className={`mode-badge ${llmOn ? 'on' : ''}`} title={llmOn ? '' : health?.llm?.error || ''}>
            <span className={`dot ${llmOn ? 'dot-ok' : 'dot-off'}`} />
            {llmOn ? `${llmName(health.llm)}` : 'Agent local'}
          </span>
          {!empty && <button className="btn btn-ghost btn-sm" onClick={() => setTurns([])} disabled={running}>Nouvelle conversation</button>}
        </div>
      </header>

      {wardrobe.length < 2 && (
        <div className="nudge"><Icon name="hanger" /><p><strong>Votre garde-robe est presque vide.</strong> Le conseiller s’appuie sur vos pièces.</p>
          <button className="btn btn-primary btn-sm" onClick={openStarter}>Garde-robe de départ</button></div>
      )}

      {empty && (
        <section className="shortcuts">
          {SHORTCUTS.map((s) => (
            <button key={s.title} className="shortcut" onClick={() => send(s.text, s.mission)} disabled={running}>
              <Icon name={s.icon} size={20} />
              <strong>{s.title}</strong>
              <span>{s.text}</span>
            </button>
          ))}
        </section>
      )}

      <section className="thread" aria-live="polite">
        {turns.map((turn, n) => (
          <Turn key={turn.id} turn={turn} active={running && n === turns.length - 1} addToWardrobe={addToWardrobe} go={go} />
        ))}
        <div ref={endRef} />
      </section>

      {!empty && !running && (
        <div className="followups">
          {SHORTCUTS.filter((s) => s.mission !== turns[turns.length - 1]?.mission).slice(0, 4).map((s) => (
            <button key={s.title} className="chip chip-btn" onClick={() => send(s.text, s.mission)}>{s.title}</button>
          ))}
        </div>
      )}

      <form className="composer" onSubmit={(e) => { e.preventDefault(); send(text); }}>
        {photo && (
          <div className="composer-photo">
            <img src={photo} alt="Photo jointe" />
            <button type="button" className="icon-btn" onClick={() => setPhoto(null)} aria-label="Retirer la photo"><Icon name="close" size={14} /></button>
          </div>
        )}
        <button type="button" className="icon-btn" onClick={() => setCamera(true)} aria-label="Prendre une photo" title="Prendre une photo"><Icon name="camera" /></button>
        <button type="button" className="icon-btn" onClick={() => fileRef.current?.click()} aria-label="Joindre une photo" title="Joindre une photo"><Icon name="upload" /></button>
        <input ref={fileRef} type="file" accept="image/*" hidden onChange={pickFile} />
        <textarea rows={1} value={text} onChange={(e) => setText(e.target.value)} maxLength={2000}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(text); } }}
          placeholder={empty ? 'Ex. « Que porter pour un mariage cet été ? »' : 'Votre question…'} aria-label="Votre question" />
        {running
          ? <button type="button" className="btn btn-ghost" onClick={() => abortRef.current?.abort()}>Arrêter</button>
          : <button type="submit" className="btn btn-primary" disabled={!text.trim() && !photo}><Icon name="arrow" /></button>}
      </form>

      <CameraModal open={camera} onClose={() => setCamera(false)} onCapture={(dataUrl) => { setPhoto(dataUrl); setCamera(false); }} />
    </div>
  );
}

function Turn({ turn, active, addToWardrobe, go }) {
  const [open, setOpen] = useState(false);
  const ids = turn.plan?.length ? turn.plan.map((p) => p.id) : turn.order;
  const titles = Object.fromEntries((turn.plan || []).map((p) => [p.id, p.title]));
  const done = ids.filter((id) => turn.steps[id]?.status === 'done').length;
  const showSteps = open || (active && !turn.final);

  return (
    <article className="turn">
      <div className="bubble user">
        {turn.photo && <img src={turn.photo} alt="" className="bubble-photo" />}
        {turn.question}
      </div>
      <div className="bubble assistant">
        <button className="reasoning-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={showSteps}>
          {active && !turn.final ? <span className="spinner" /> : <Icon name="agent" size={16} />}
          {active && !turn.final ? 'Le conseiller réfléchit…' : `Raisonnement · ${done || ids.length} étape${(done || ids.length) > 1 ? 's' : ''}`}
          {turn.mode && <span className="tag">{MODE_NAMES[turn.mode] || turn.mode}</span>}
        </button>
        {showSteps && (
          <ol className="timeline compact">
            {ids.map((id) => {
              const step = turn.steps[id] || {};
              const status = step.status || (turn.error ? 'skipped' : 'pending');
              return (
                <li key={id} className={`tl-${status}`}>
                  <span className="tl-icon">{status === 'running' ? <span className="spinner" /> : status === 'done' ? <Icon name="check" size={12} strokeWidth={2.5} /> : status === 'skipped' ? '–' : ''}</span>
                  <div className="tl-body"><strong>{titles[id] || step.title}</strong>{step.summary && <p>{step.summary}</p>}</div>
                </li>
              );
            })}
          </ol>
        )}
        {turn.notice && <div className="banner banner-warn">{turn.notice}</div>}
        {turn.error && <div className="banner banner-bad">{turn.error}</div>}
        {turn.final && <Answer final={turn.final} addToWardrobe={addToWardrobe} go={go} />}
      </div>
    </article>
  );
}

function Answer({ final, addToWardrobe, go }) {
  const tone = VERDICTS[final.verdict]?.tone;
  const health = final.insights?.health ?? (final.mission === 'audit' ? final.score : null);
  return (
    <div className="answer-block">
      {(final.verdict || health != null) && (
        <div className="answer-head">
          {final.verdict && <ScoreRing value={final.score} tone={tone} size={76} label="redond." />}
          {!final.verdict && health != null && <ScoreRing value={health} tone={health >= 75 ? 'good' : health >= 50 ? 'warn' : 'bad'} size={76} label="santé" />}
          <div>
            {final.verdict && <VerdictPill verdict={final.verdict} />}
            <strong>{final.headline}</strong>
          </div>
        </div>
      )}
      {final.answer && <p className="answer">{final.answer}</p>}
      {!final.answer && final.reasons?.length > 0 && <ul className="check-list">{final.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
      {final.answer && final.actions?.length > 0 && !final.usage && (
        <ul className="check-list action">{final.actions.map((a) => <li key={a}>{a}</li>)}</ul>
      )}

      {final.outfits?.length > 0 && (
        <div className="cards-block">
          <h4>Tenues proposées</h4>
          {final.outfits.map((o, i) => (
            <div key={i} className="outfit-row">
              <span className="outfit-n">{i + 1}</span>
              {o.pieces.map((p) => <figure key={p.id} className="thumb"><img src={asset(p.image_url)} alt={p.name} /><figcaption>{p.name}</figcaption></figure>)}
            </div>
          ))}
        </div>
      )}

      {final.similar_owned?.length > 0 && (
        <div className="cards-block">
          <h4>Déjà dans votre garde-robe</h4>
          <div className="thumb-row">{final.similar_owned.map((m) => (
            <figure key={m.id || m.name} className="thumb"><img src={asset(m.image_url)} alt={m.name} /><figcaption>{Math.round(m.similarity * 100)} % · {m.name}</figcaption></figure>))}</div>
        </div>
      )}

      {final.duplicates?.length > 0 && (
        <div className="cards-block">
          <h4>Doublons</h4>
          {final.duplicates.slice(0, 4).map((g) => (
            <div key={g.keep} className="outfit-row">
              {g.items.map((p) => (
                <figure key={p.id} className={`thumb ${p.id === g.keep ? 'keep' : 'extra'}`}><img src={asset(p.image_url)} alt={p.name} />
                  <figcaption>{p.id === g.keep ? 'À garder' : 'En trop'}</figcaption></figure>))}
            </div>
          ))}
          <button className="btn btn-ghost btn-sm" onClick={() => go('stats')}>Gérer dans le tableau de bord <Icon name="arrow" size={14} /></button>
        </div>
      )}

      {final.suggestions?.length > 0 && (
        <div className="cards-block">
          <h4>{final.mission === 'purchase' || final.verdict ? 'Alternatives du catalogue' : 'Achats utiles'}</h4>
          <div className="card-grid">
            {final.suggestions.slice(0, 4).map((p) => (
              <ItemCard key={p.id} item={{ ...p, color: p.color || p.primary_color }} compact>
                {p.reason && <p className="tip">{p.reason}</p>}
                <button className="btn btn-ghost btn-sm" onClick={() => addToWardrobe({ product_id: p.id }, p.name)}>
                  <Icon name="plus" size={14} /> Je l’ai acheté
                </button>
              </ItemCard>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

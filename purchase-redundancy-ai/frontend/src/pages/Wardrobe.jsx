import React, { useEffect, useState } from 'react';
import { api, asset, errorMessage } from '../api';
import Icon from '../components/Icon';
import WardrobeNudges from '../components/Nudges';
import { Empty, Field, ItemCard, PhotoPicker, Select } from '../components/ui';
import { CATEGORIES, COLORS, MATERIALS, STYLES, formatPrice, materialLabel, styleLabel } from '../labels';

export default function Wardrobe({ wardrobe, refreshWardrobe, refreshStatus, addToWardrobe, notify, go, openStarter, openProfile, user, addRequest }) {
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');
  const [adding, setAdding] = useState(false);
  useEffect(() => { if (addRequest) setAdding(true); }, [addRequest]);  // "+ Ajouter une pièce" in the sidebar
  const [editing, setEditing] = useState(null);
  const [busy, setBusy] = useState(false);

  const counts = wardrobe.reduce((acc, i) => ({ ...acc, [i.category]: (acc[i.category] || 0) + 1 }), {});
  const term = search.trim().toLowerCase();
  const shown = wardrobe
    .filter((i) => filter === 'all' || i.category === filter)
    .filter((i) => !term || [i.name, i.brand, i.color, i.material].some((v) => (v || '').toLowerCase().includes(term)));
  const totalValue = wardrobe.reduce((sum, i) => sum + (Number(i.price) || 0), 0);

  const remove = async (item) => {
    try {
      await api.delete(`/wardrobe/${item.id}`);
      await refreshWardrobe();
      notify(`« ${item.name} » retiré`, 'info');
    } catch (e) {
      notify(errorMessage(e), 'bad');
    }
  };

  const bulk = async (action) => {
    if (action === 'clear' && !window.confirm('Vider toute la garde-robe ?')) return;
    setBusy(true);
    try {
      await api.delete('/wardrobe');
      await Promise.all([refreshWardrobe(), refreshStatus()]);
    } catch (e) {
      notify(errorMessage(e), 'bad');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Ma garde-robe</h2>
          <p>
            {wardrobe.length} pièce{wardrobe.length > 1 ? 's' : ''}
            {totalValue > 0 && <> · valeur {formatPrice(Math.round(totalValue))}</>} — touchez une pièce pour la modifier.
          </p>
        </div>
        <div className="head-actions">
          <button className="btn btn-ghost" onClick={openStarter} disabled={busy}><Icon name="sparkle" /> Garde-robe de départ</button>
          {wardrobe.length > 0 && <button className="btn btn-ghost" onClick={() => bulk('clear')} disabled={busy}>Vider</button>}
          <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="plus" /> Ajouter une pièce</button>
        </div>
      </header>

      <WardrobeNudges user={user} wardrobe={wardrobe} openStarter={openStarter} openProfile={openProfile} />

      {wardrobe.length > 0 && (
        <div className="filter-row">
          <div className="filter-chips">
            <button className={`chip chip-btn ${filter === 'all' ? 'active' : ''}`} onClick={() => setFilter('all')}>Tout · {wardrobe.length}</button>
            {CATEGORIES.filter((c) => counts[c.value]).map((c) => (
              <button key={c.value} className={`chip chip-btn ${filter === c.value ? 'active' : ''}`} onClick={() => setFilter(c.value)}>
                {c.label} · {counts[c.value]}
              </button>
            ))}
          </div>
          <div className="search-bar small-search">
            <Icon name="search" size={16} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Rechercher une pièce…" />
          </div>
        </div>
      )}

      {wardrobe.length === 0 ? (
        <Empty title="Votre garde-robe est vide">
          <p>Photographiez vos vêtements, ajoutez-les depuis le catalogue, ou ajoutez une garde-robe de départ.</p>
          <div className="empty-actions">
            <button className="btn btn-primary" onClick={() => setAdding(true)}><Icon name="camera" /> Ajouter en photo</button>
            <button className="btn btn-ghost" onClick={() => go('catalog')}>Parcourir le catalogue</button>
          </div>
        </Empty>
      ) : (
        <div className="card-grid wardrobe-grid">
          {shown.map((item) => (
            <ItemCard key={item.id} item={item} onClick={() => setEditing(item)}>
              <p className="item-tags">{styleLabel(item.style)} · {materialLabel(item.material)}</p>
              <button className="icon-btn danger card-delete" aria-label={`Retirer ${item.name}`}
                onClick={(e) => { e.stopPropagation(); remove(item); }}>
                <Icon name="trash" size={16} />
              </button>
            </ItemCard>
          ))}
          {shown.length === 0 && <p className="muted">Aucune pièce ne correspond à « {search} ».</p>}
        </div>
      )}

      {adding && <AddItemModal onClose={() => setAdding(false)} addToWardrobe={addToWardrobe} go={go} />}
      {editing && <EditItemModal item={editing} onClose={() => setEditing(null)} notify={notify}
        onSaved={refreshWardrobe} onDelete={() => { remove(editing); setEditing(null); }} />}
    </div>
  );
}

function AddItemModal({ onClose, addToWardrobe, go }) {
  const [photo, setPhoto] = useState(null);
  const [form, setForm] = useState({ name: '', category: '', color: '', style: '', material: '', price: '' });
  const [saving, setSaving] = useState(false);
  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const save = async () => {
    setSaving(true);
    const payload = Object.fromEntries(Object.entries(form).filter(([, v]) => v !== ''));
    if (payload.price) payload.price = parseFloat(payload.price);
    if (photo) payload.image_base64 = photo;
    const created = await addToWardrobe(payload);
    setSaving(false);
    if (created) onClose();
  };

  const canSave = photo || (form.name && form.category);

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Ajouter une pièce">
        <header className="modal-head">
          <h3>Ajouter une pièce</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
        </header>
        <div className="modal-body add-grid">
          <PhotoPicker value={photo} onChange={setPhoto} hint="Photo du vêtement — catégorie, couleur et style détectés automatiquement" />
          <div className="add-form">
            <Field label="Nom (optionnel avec une photo)">
              <input value={form.name} onChange={(e) => set('name')(e.target.value)} placeholder="ex. Jean brut slim" />
            </Field>
            <div className="form-row">
              <Field label="Catégorie"><Select value={form.category} onChange={set('category')} options={CATEGORIES} placeholder={photo ? 'Auto' : 'Choisir…'} /></Field>
              <Field label="Couleur"><Select value={form.color} onChange={set('color')} options={COLORS} placeholder={photo ? 'Auto' : 'Choisir…'} /></Field>
            </div>
            <div className="form-row">
              <Field label="Style"><Select value={form.style} onChange={set('style')} options={STYLES} placeholder="Auto" /></Field>
              <Field label="Matière"><Select value={form.material} onChange={set('material')} options={MATERIALS} placeholder="Auto" /></Field>
            </div>
            <Field label="Prix payé (optionnel)">
              <input type="number" min="0" value={form.price} onChange={(e) => set('price')(e.target.value)} />
            </Field>
            <p className="muted small">Ou choisissez un produit existant dans le <button className="link" onClick={() => { onClose(); go('catalog'); }}>catalogue</button>.</p>
          </div>
        </div>
        <footer className="modal-foot">
          <button className="btn btn-ghost" onClick={onClose}>Annuler</button>
          <button className="btn btn-primary" onClick={save} disabled={!canSave || saving}>
            {saving ? <><span className="spinner" /> Analyse de la photo…</> : <><Icon name="check" /> Ajouter</>}
          </button>
        </footer>
      </div>
    </div>
  );
}


function EditItemModal({ item, onClose, onSaved, onDelete, notify }) {
  const [form, setForm] = useState({
    name: item.name || '', category: item.category || '', color: item.color || '', style: item.style || '',
    material: item.material || '', brand: item.brand || '', price: item.price ?? '',
  });
  const [saving, setSaving] = useState(false);
  const set = (key) => (value) => setForm((f) => ({ ...f, [key]: value }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = { ...form, price: form.price === '' ? null : parseFloat(form.price) };
      if (payload.price === null) delete payload.price;
      await api.patch(`/wardrobe/${item.id}`, payload);
      await onSaved();
      notify('Pièce mise à jour', 'good');
      onClose();
    } catch (e) {
      notify(errorMessage(e), 'bad');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Modifier la pièce">
        <header className="modal-head">
          <h3>Modifier la pièce</h3>
          <button className="icon-btn" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
        </header>
        <div className="modal-body add-grid">
          <div className="edit-photo">{item.image_url && <img src={asset(item.image_url)} alt={item.name} />}</div>
          <div className="add-form">
            <Field label="Nom"><input value={form.name} onChange={(e) => set('name')(e.target.value)} /></Field>
            <div className="form-row">
              <Field label="Catégorie"><Select value={form.category} onChange={set('category')} options={CATEGORIES} /></Field>
              <Field label="Couleur"><Select value={form.color} onChange={set('color')} options={withCurrent(COLORS, form.color)} /></Field>
            </div>
            <div className="form-row">
              <Field label="Style"><Select value={form.style} onChange={set('style')} options={withCurrent(STYLES, form.style)} /></Field>
              <Field label="Matière"><Select value={form.material} onChange={set('material')} options={withCurrent(MATERIALS, form.material)} placeholder="—" /></Field>
            </div>
            <div className="form-row">
              <Field label="Marque"><input value={form.brand} onChange={(e) => set('brand')(e.target.value)} /></Field>
              <Field label="Prix payé"><input type="number" min="0" value={form.price} onChange={(e) => set('price')(e.target.value)} /></Field>
            </div>
          </div>
        </div>
        <footer className="modal-foot">
          <button className="btn btn-ghost danger-text" onClick={onDelete}><Icon name="trash" /> Retirer</button>
          <span className="spacer" />
          <button className="btn btn-ghost" onClick={onClose}>Annuler</button>
          <button className="btn btn-primary" onClick={save} disabled={saving || !form.name}>
            {saving ? <span className="spinner" /> : <Icon name="check" />} Enregistrer
          </button>
        </footer>
      </div>
    </div>
  );
}

/** Keep values that come from the photo/catalog selectable even if they are not in the short list */
function withCurrent(options, value) {
  return value && !options.some((o) => o.value === value) ? [...options, { value, label: value }] : options;
}

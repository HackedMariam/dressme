import React, { useEffect, useState } from 'react';
import { api, asset, errorMessage, resizeImage } from '../api';
import { track } from '../utils/analytics';
import Icon from '../components/Icon';
import { ColorDot, Empty, ItemCard, ScoreRing, VerdictPill } from '../components/ui';
import { CATEGORIES, VERDICTS, categoryLabel, colorLabel, formatPrice, materialLabel, seasonLabel, styleLabel } from '../labels';

const PAGE = 48;

const SORTS = [
  { value: 'relevance', label: 'Pertinence' },
  { value: 'price_asc', label: 'Prix croissant' },
  { value: 'price_desc', label: 'Prix décroissant' },
  { value: 'name', label: 'Nom (A → Z)' },
];

export default function Catalog({ addToWardrobe, notify, wardrobe, stats, refreshStatus, markAnalysis, user, catalogPreset }) {
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [category, setCategory] = useState(catalogPreset?.category || '');
  const [color, setColor] = useState(catalogPreset?.color || '');
  const [source, setSource] = useState('');
  const [priced, setPriced] = useState(false);
  const [sort, setSort] = useState('relevance');
  const [forGender, setForGender] = useState(['Women', 'Men'].includes(user?.gender) ? user.gender : '');
  const [products, setProducts] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [photo, setPhoto] = useState(null);           // photo search: { url, matches }
  const [searchingPhoto, setSearchingPhoto] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(query.trim()), 350);
    return () => clearTimeout(t);
  }, [query]);

  const load = async (offset = 0) => {
    setLoading(true);
    try {
      const params = { limit: PAGE, offset };
      if (category) params.category = category;
      if (debounced) params.q = debounced;
      if (source) params.source = source;
      if (priced) params.priced = true;
      if (sort !== 'relevance') params.sort = sort;
      if (forGender) params.gender = forGender;
      if (color) params.color = color;
      const { data } = await api.get('/products', { params });
      setProducts((prev) => (offset ? [...prev, ...data.products] : data.products));
      setTotal(data.total);
    } catch (e) {
      notify(errorMessage(e), 'bad');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(0); }, [debounced, category, source, priced, sort, forGender, color]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (debounced) track('catalog_search', 'catalog'); }, [debounced]);

  const owned = new Set(wardrobe.map((w) => w.product_id).filter(Boolean));
  const sources = Object.entries(stats?.sources || {});

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Trouver similaire</h2>
          <p>
            Décrivez ou photographiez un vêtement : la vision CLIP retrouve les plus proches parmi {stats?.products_in_catalog ?? '…'} vrais produits
            {sources.length > 1 && ` (${sources.length} sources)`}. Touchez un produit pour savoir si vous l’avez déjà.
          </p>
        </div>
        <div className="photo-search">
          {photo && <img src={photo.url} alt="Photo recherchée" />}
          {photo && <button className="btn btn-ghost btn-sm" onClick={() => setPhoto(null)}>Effacer</button>}
          <label className="btn btn-dark">
            {searchingPhoto ? <span className="spinner" /> : <Icon name="camera" size={16} />} Chercher par photo
            <input type="file" accept="image/*" hidden onChange={async (e) => {
              const file = e.target.files?.[0];
              e.target.value = '';
              if (!file) return;
              setSearchingPhoto(true);
              try {
                const url = await resizeImage(file);
                const { data } = await api.post('/camera-capture', { image_base64: url, top_k: 24 });
                setPhoto({ url, matches: data.catalog_matches });
                track('photo_search', 'catalog', { results: data.catalog_matches.length });
              } catch (err) {
                notify(errorMessage(err), 'bad');
              } finally {
                setSearchingPhoto(false);
              }
            }} />
          </label>
        </div>
      </header>

      {photo && (
        <section className="card">
          <h3>Les plus proches de votre photo</h3>
          {photo.matches.length === 0 ? <p className="muted">Aucun produit assez proche.</p> : (
            <div className="card-grid catalog-grid" style={{ marginTop: 12 }}>
              {photo.matches.map((p) => (
                <ItemCard key={p.id} item={p} badge={`${Math.round(p.similarity * 100)}%`}
                  onClick={() => setSelected({ ...p, primary_color: p.color })}>
                  {owned.has(p.id) && <p className="item-source">Déjà dans votre garde-robe</p>}
                </ItemCard>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="search-bar">
        <Icon name="search" />
        <input value={query} onChange={(e) => setQuery(e.target.value)}
          placeholder="Recherche par la vision CLIP, en anglais : « black leather boots », « floral summer dress »…" />
        {loading && <span className="spinner" />}
      </div>

      <div className="filter-row">
        <div className="filter-chips">
          <button className={`chip chip-btn ${!category ? 'active' : ''}`} onClick={() => setCategory('')}>Tout</button>
          {CATEGORIES.map((c) => (
            <button key={c.value} className={`chip chip-btn ${category === c.value ? 'active' : ''}`} onClick={() => setCategory(c.value)}>{c.label}</button>
          ))}
        </div>
        <div className="filter-chips">
          {sources.length > 1 && (
            <select className="chip-select" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source">
              <option value="">Toutes les sources</option>
              {sources.map(([name, count]) => <option key={name} value={name.split(' ')[0]}>{name} ({count})</option>)}
            </select>
          )}
          {color && (
            <button className="chip chip-btn active" onClick={() => setColor('')} aria-label="Retirer le filtre couleur">
              <ColorDot color={color} /> {colorLabel(color)} <Icon name="close" size={12} />
            </button>
          )}
          <label className="chip chip-toggle">
            <input type="checkbox" checked={priced} onChange={(e) => setPriced(e.target.checked)} /> Avec prix
          </label>
          <select className="chip-select" value={forGender} onChange={(e) => setForGender(e.target.value)} aria-label="Pour">
            <option value="">Femme et homme</option>
            <option value="Women">Pour femme</option>
            <option value="Men">Pour homme</option>
          </select>
          <select className="chip-select" value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Trier">
            {SORTS.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </select>
        </div>
      </div>

      {!loading && products.length === 0 ? (
        <Empty icon="search" title="Aucun produit" />
      ) : (
        <div className="card-grid catalog-grid">
          {products.map((p) => (
            <ItemCard key={p.id} item={{ ...p, color: p.primary_color }} onClick={() => setSelected(p)}
              badge={p.similarity !== undefined ? `${Math.round(p.similarity * 100)}%` : owned.has(p.id) ? 'Possédé' : null}>
              <p className="item-source">{shortSource(p.data_source)}</p>
            </ItemCard>
          ))}
        </div>
      )}

      {products.length < total && (
        <div className="center">
          <button className="btn btn-ghost" onClick={() => load(products.length)} disabled={loading}>
            Voir plus ({total - products.length} restants)
          </button>
        </div>
      )}

      {selected && (
        <ProductModal product={selected} owned={owned.has(selected.id)} onClose={() => setSelected(null)}
          addToWardrobe={addToWardrobe} notify={notify} refreshStatus={refreshStatus} markAnalysis={markAnalysis} />
      )}
    </div>
  );
}

function ProductModal({ product, owned, onClose, addToWardrobe, notify, refreshStatus, markAnalysis }) {
  const [check, setCheck] = useState(null);
  const [checking, setChecking] = useState(false);
  const [isOwned, setIsOwned] = useState(owned);

  const runCheck = async () => {
    setChecking(true);
    try {
      const item = {
        name: product.name, category: product.category, color: product.primary_color,
        style: product.style || 'casual', material: product.material, price: product.price,
      };
      markAnalysis?.();
      const { data } = await api.post('/analyze', { new_item: item, product_id: product.id, language: 'fr' });
      setCheck(data);
      track('analysis_done', 'catalog', { verdict: data.recommendation, category: product.category });
      refreshStatus();
    } catch (e) {
      notify(errorMessage(e), 'bad');
    } finally {
      setChecking(false);
    }
  };

  const add = async () => {
    if (await addToWardrobe({ product_id: product.id }, product.name)) setIsOwned(true);
  };

  const tone = check ? VERDICTS[check.recommendation]?.tone : null;

  return (
    <div className="modal-backdrop" onClick={onClose} role="presentation">
      <div className="modal product-modal" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={product.name}>
        <button className="icon-btn modal-close" onClick={onClose} aria-label="Fermer"><Icon name="close" /></button>
        <div className="product-layout">
          <div className="product-photo">
            <img src={asset(product.image_url)} alt={product.name} />
          </div>
          <div className="product-info">
            <span className="eyebrow">{categoryLabel(product.category)}{product.brand ? ` · ${product.brand}` : ''}</span>
            <h3>{product.name}</h3>
            <p className="product-price">{product.price ? formatPrice(product.price) : <span className="muted">Prix non publié par la source</span>}</p>

            <dl className="specs">
              <dt>Couleur</dt><dd><ColorDot color={product.primary_color} /> {colorLabel(product.primary_color)}</dd>
              <dt>Matière</dt><dd>{product.material ? materialLabel(product.material) : '—'}</dd>
              <dt>Style</dt><dd>{styleLabel(product.style)}</dd>
              {product.gender && <><dt>Pour</dt><dd>{{ Men: 'Homme', Women: 'Femme', Boys: 'Garçon', Girls: 'Fille', Kids: 'Enfant', Unisex: 'Mixte' }[product.gender] || product.gender}</dd></>}
              {product.season && <><dt>Saison</dt><dd>{seasonLabel(product.season)}</dd></>}
            </dl>

            {product.description && product.description !== product.name && <p className="product-desc">{product.description}</p>}

            <div className="product-actions">
              <button className="btn btn-primary" onClick={runCheck} disabled={checking}>
                {checking ? <><span className="spinner" /> Comparaison…</> : <><Icon name="scan" /> Ai-je déjà ça ?</>}
              </button>
              {isOwned ? <span className="tag">Dans ma garde-robe</span> : (
                <button className="btn btn-ghost" onClick={add}><Icon name="plus" /> Je l’ai déjà</button>
              )}
            </div>

            {check && (
              <div className={`check-result tone-${tone}`}>
                <ScoreRing value={check.redundancy_score} tone={tone} size={84} label="redond." />
                <div>
                  <VerdictPill verdict={check.recommendation} />
                  <p>{check.similar_items[0]
                    ? <>Ressemble à <strong>{check.similar_items[0].name}</strong> ({Math.round(check.similar_items[0].similarity * 100)}%).</>
                    : 'Rien de similaire dans votre garde-robe.'}</p>
                </div>
                {check.similar_items[0]?.image_url && <img src={asset(check.similar_items[0].image_url)} alt="" className="check-thumb" />}
              </div>
            )}

            <p className="source-line">
              Source : {product.data_source || 'catalogue illustré'}
              {product.source_license && ` · licence ${product.source_license}`}
              {product.source_url && <> · <a href={product.source_url} target="_blank" rel="noreferrer">voir l’origine</a></>}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

function shortSource(source) {
  if (!source) return 'Illustration';
  return source.replace(' (Hugging Face)', '').replace('Marqo/', '');
}

// French labels for values the backend stores in English

export const CATEGORIES = [
  { value: 'shirts', label: 'Hauts' },
  { value: 'pants', label: 'Bas' },
  { value: 'dresses', label: 'Robes' },
  { value: 'shoes', label: 'Chaussures' },
  { value: 'outerwear', label: 'Vestes & manteaux' },
  { value: 'accessories', label: 'Accessoires' },
];

export const COLORS = [
  { value: 'black', label: 'Noir', hex: '#1f1f24' },
  { value: 'white', label: 'Blanc', hex: '#f7f7f5' },
  { value: 'gray', label: 'Gris', hex: '#8a8d93' },
  { value: 'navy', label: 'Bleu marine', hex: '#1f2a5a' },
  { value: 'blue', label: 'Bleu', hex: '#2f6fd6' },
  { value: 'beige', label: 'Beige', hex: '#e3d5b8' },
  { value: 'brown', label: 'Marron', hex: '#7b4a2d' },
  { value: 'khaki', label: 'Kaki', hex: '#c9b47a' },
  { value: 'green', label: 'Vert', hex: '#2f8f4e' },
  { value: 'olive', label: 'Olive', hex: '#6f7436' },
  { value: 'red', label: 'Rouge', hex: '#d23b3b' },
  { value: 'burgundy', label: 'Bordeaux', hex: '#7a1f33' },
  { value: 'pink', label: 'Rose', hex: '#f2a7c3' },
  { value: 'orange', label: 'Orange', hex: '#f08a2c' },
  { value: 'yellow', label: 'Jaune', hex: '#f4d03f' },
  { value: 'purple', label: 'Violet', hex: '#7d3c98' },
  { value: 'teal', label: 'Bleu canard', hex: '#1f8a8a' },
];

export const STYLES = [
  { value: 'casual', label: 'Décontracté' },
  { value: 'formal', label: 'Habillé' },
  { value: 'business', label: 'Bureau' },
  { value: 'classic', label: 'Classique' },
  { value: 'minimalist', label: 'Minimaliste' },
  { value: 'sporty', label: 'Sport' },
  { value: 'streetwear', label: 'Streetwear' },
  { value: 'vintage', label: 'Vintage' },
  { value: 'bohemian', label: 'Bohème' },
  { value: 'trendy', label: 'Tendance' },
];

export const MATERIALS = [
  { value: 'cotton', label: 'Coton' },
  { value: 'denim', label: 'Denim' },
  { value: 'wool', label: 'Laine' },
  { value: 'leather', label: 'Cuir' },
  { value: 'linen', label: 'Lin' },
  { value: 'silk', label: 'Soie' },
  { value: 'polyester', label: 'Polyester' },
  { value: 'knit', label: 'Maille' },
  { value: 'suede', label: 'Daim' },
  { value: 'nylon', label: 'Nylon' },
];

export const VERDICTS = {
  buy: { label: 'Achat conseillé', tone: 'good', icon: '✓' },
  consider: { label: 'À réfléchir', tone: 'warn', icon: '!' },
  skip: { label: 'Vous l’avez déjà', tone: 'bad', icon: '✕' },
};

const lookup = (list) => Object.fromEntries(list.map((o) => [o.value, o.label]));
const CATEGORY_LABEL = lookup(CATEGORIES);
const COLOR_LABEL = lookup(COLORS);
const STYLE_LABEL = lookup(STYLES);
const MATERIAL_LABEL = lookup(MATERIALS);

export const categoryLabel = (v) => CATEGORY_LABEL[v] || v || '—';
export const colorLabel = (v) => COLOR_LABEL[v] || v || '—';
const EXTRA_STYLES = { preppy: 'Preppy', edgy: 'Rock', romantic: 'Romantique', athletic: 'Athlétique', luxury: 'Luxe' };
export const styleLabel = (v) => STYLE_LABEL[v] || EXTRA_STYLES[v] || v || '—';
const EXTRA_MATERIALS = {
  jersey: 'Jersey', fleece: 'Polaire', blend: 'Mélange', spandex: 'Élasthanne', viscose: 'Viscose',
  bamboo: 'Bambou', acrylic: 'Acrylique', rayon: 'Rayonne', hemp: 'Chanvre',
};
export const materialLabel = (v) => MATERIAL_LABEL[v] || EXTRA_MATERIALS[v] || v || '—';
// every catalog color (some are not offered in the pickers)
const EXTRA_HEX = {
  cream: '#f4ecd6', tan: '#cfa77a', maroon: '#6e1f22', turquoise: '#3cc7c0', coral: '#ff7f61', salmon: '#f59a86',
  gold: '#d4af37', silver: '#c0c4c8', peach: '#ffc9a8', lavender: '#c9b8ea', lime: '#9bd13d', mint: '#a8e6c9',
  'forest green': '#235c3a', emerald: '#2fae74', cobalt: '#1f4fbf', 'royal blue': '#3557d4',
};
export const colorHex = (v) => COLORS.find((c) => c.value === v)?.hex || EXTRA_HEX[v] || '#c4c7cf';

export const formatPrice = (p) => (p || p === 0) && Number.isFinite(Number(p))
  ? `${Number(p).toFixed(Number(p) % 1 ? 2 : 0)} $` : '';  // catalog prices are in USD

/** "GPT-4.1" / "Claude" from the /health llm status */
export const llmName = (llm) => (llm?.provider === 'openai' ? (llm.model || 'GPT').toUpperCase() : 'Claude');

const SEASONS = { spring: 'Printemps', summer: 'Été', fall: 'Automne', winter: 'Hiver', 'all-season': 'Toutes saisons' };
export const seasonLabel = (v) => SEASONS[(v || '').toLowerCase()] || v || '—';

// ---------- profile (sign-up form) ----------

export const GENDERS = [
  { value: 'Women', label: 'Femme' },
  { value: 'Men', label: 'Homme' },
  { value: 'Unspecified', label: 'Non précisé' },
];
export const CLOTHING_SIZES = ['XS', 'S', 'M', 'L', 'XL', 'XXL'].map((s) => ({ value: s, label: s }));
export const SHOE_SIZES = Array.from({ length: 14 }, (_, i) => String(35 + i)).map((s) => ({ value: s, label: s }));
// Styles the catalog actually uses come first
export const PROFILE_STYLES = ['casual', 'sporty', 'formal', 'classic', 'business', 'minimalist', 'streetwear', 'vintage', 'bohemian', 'trendy']
  .map((v) => STYLES.find((s) => s.value === v));
export const genderLabel = (v) => GENDERS.find((g) => g.value === v)?.label || '—';

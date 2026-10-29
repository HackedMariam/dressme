"""Rendu markdown de la page (static/markdown.js), exécuté avec Node et un DOM minimal simulé."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node.js absent")
MARKDOWN_JS = Path(__file__).resolve().parents[1] / "static" / "markdown.js"

# DOM minimal : createElement / createTextNode / fragment / textContent. Pas d'innerHTML : s'il était
# utilisé, l'appel échouerait. On sérialise ensuite l'arbre en échappant le texte, comme un navigateur.
HARNESS = r"""
const md = require(process.argv[1]);
function node(tag) { return { tag, children: [], text: null,
  appendChild(c) { this.children.push(c); return c; },
  set textContent(v) { this.children = [{ tag: "#text", text: String(v), children: [] }]; } }; }
const doc = { createElement: (t) => node(t), createTextNode: (v) => ({ tag: "#text", text: String(v), children: [] }),
              createDocumentFragment: () => node("#fragment") };
const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
function html(n) { if (n.tag === "#text") return esc(n.text);
  const inner = n.children.map(html).join(""); return n.tag === "#fragment" ? inner : `<${n.tag}>${inner}</${n.tag}>`; }
function tags(n, out) { if (n.tag !== "#text" && n.tag !== "#fragment") out.push(n.tag); n.children.forEach((c) => tags(c, out)); return out; }
const text = JSON.parse(process.argv[2]);
const frag = md.render(text, doc);
process.stdout.write(JSON.stringify({ html: html(frag), tags: tags(frag, []) }));
"""


def render(text):
    out = subprocess.run(["node", "-e", HARNESS, str(MARKDOWN_JS), json.dumps(text)], capture_output=True,
                         text=True, encoding="utf-8")
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def test_bold_lists_and_paragraphs():
    result = render("**Contexte** : travail.\n\nVoici :\n- un *haut*\n- un `bas`\n\n1. Robe\n2. Veste")
    assert result["html"] == ("<p><strong>Contexte</strong> : travail.</p><p>Voici :</p>"
                              "<ul><li>un <em>haut</em></li><li>un <code>bas</code></li></ul>"
                              "<ol><li>Robe</li><li>Veste</li></ol>")


def test_html_from_a_service_is_never_interpreted():
    attack = '<img src=x onerror="alert(1)"> **<script>alert(2)</script>** [lien](javascript:alert(3))'
    result = render(attack)
    assert set(result["tags"]) <= {"p", "strong", "em", "code", "ul", "ol", "li", "h4", "br"}
    assert "<img" not in result["html"] and "<script>" not in result["html"]
    assert "&lt;img src=x onerror=\"alert(1)\"&gt;" in result["html"]
    assert "<strong>&lt;script&gt;alert(2)&lt;/script&gt;</strong>" in result["html"]


def test_line_breaks_inside_a_paragraph():
    assert render("ligne 1\nligne 2")["html"] == "<p>ligne 1<br></br>ligne 2</p>"


def test_heading_and_empty_text():
    assert render("### Titre")["html"] == "<h4>Titre</h4>"
    assert render("")["html"] == ""


def test_markdown_js_has_no_inner_html():
    source = MARKDOWN_JS.read_text(encoding="utf-8")
    assert "innerHTML" not in source and "insertAdjacentHTML" not in source


def test_numbered_items_separated_by_blank_lines_stay_one_list():
    # Format typique de BO5 : une ligne vide entre chaque élément numéroté.
    result = render("Guide :\n\n1. **Haut** : col roulé.\n\n2. **Bas** : pantalon large.\n\n3. Bottines.\n\nConclusion.")
    assert result["html"] == ("<p>Guide :</p><ol><li><strong>Haut</strong> : col roulé.</li>"
                              "<li><strong>Bas</strong> : pantalon large.</li><li>Bottines.</li></ol><p>Conclusion.</p>")


def test_paragraphs_are_still_separated_by_blank_lines():
    assert render("Un.\n\nDeux.")["html"] == "<p>Un.</p><p>Deux.</p>"
    assert render("- a\n\nTexte\n- b")["html"] == "<ul><li>a</li></ul><p>Texte</p><ul><li>b</li></ul>"

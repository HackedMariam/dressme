/* Rendu markdown minimal et sûr pour les cartes de l'orchestrateur.
 *
 * parse(text) découpe le texte en blocs (paragraphes, listes, titres) et en morceaux en ligne (texte, gras,
 * italique, code). render(text, document) construit le DOM avec createElement et textContent uniquement :
 * aucun HTML venant des services n'est jamais interprété (aucune insertion de HTML brut).
 * Utilisable dans la page (window.DressMeMarkdown) et dans Node pour les tests (module.exports).
 */
(function (root) {
  "use strict";

  var BULLET = /^\s*[-*•]\s+(.*)$/;
  var ORDERED = /^\s*(\d+)[.)]\s+(.*)$/;
  var HEADING = /^\s*#{1,6}\s+(.*)$/;
  var INLINE = /(\*\*[^*\n]+\*\*|__[^_\n]+__|`[^`\n]+`|\*[^*\s][^*\n]*\*)/;

  function inline(text) {
    var parts = [];
    String(text).split(INLINE).forEach(function (piece) {
      if (!piece) return;
      if (/^\*\*[^*]+\*\*$/.test(piece) || /^__[^_]+__$/.test(piece)) {
        parts.push({ t: "b", v: piece.slice(2, -2) });
      } else if (/^`[^`]+`$/.test(piece)) {
        parts.push({ t: "code", v: piece.slice(1, -1) });
      } else if (/^\*[^*\s][^*]*\*$/.test(piece)) {
        parts.push({ t: "i", v: piece.slice(1, -1) });
      } else {
        parts.push({ t: "text", v: piece });
      }
    });
    return parts;
  }

  function parse(text) {
    var blocks = [];
    var current = null;
    var gap = false;   // ligne vide vue : un paragraphe se ferme, une liste continue si l'élément suivant est du même type
    String(text == null ? "" : text).replace(/\r\n?/g, "\n").split("\n").forEach(function (line) {
      var m;
      if (!line.trim()) { gap = true; return; }
      var listItem = (m = line.match(ORDERED)) ? { type: "ol", content: m[2], n: +m[1] }
        : (m = line.match(BULLET)) ? { type: "ul", content: m[1] } : null;
      if (gap && !(listItem && current && current.type === listItem.type)) current = null;
      gap = false;
      if (listItem) {
        if (!current || current.type !== listItem.type) {
          current = { type: listItem.type, items: [] };
          if (listItem.type === "ol") current.start = listItem.n;
          blocks.push(current);
        }
        current.items.push(inline(listItem.content));
        return;
      }
      if ((m = line.match(HEADING))) {
        blocks.push({ type: "h", lines: [inline(m[1])] });
        current = null;
        return;
      }
      if (!current || current.type !== "p") { current = { type: "p", lines: [] }; blocks.push(current); }
      current.lines.push(inline(line.trim()));
    });
    return blocks;
  }

  function appendInline(doc, parent, parts) {
    parts.forEach(function (part) {
      if (part.t === "text") { parent.appendChild(doc.createTextNode(part.v)); return; }
      var el = doc.createElement(part.t === "b" ? "strong" : part.t === "i" ? "em" : "code");
      el.textContent = part.v;
      parent.appendChild(el);
    });
  }

  function render(text, doc) {
    doc = doc || root.document;
    var fragment = doc.createDocumentFragment();
    parse(text).forEach(function (block) {
      if (block.type === "ul" || block.type === "ol") {
        var list = doc.createElement(block.type);
        if (block.start && block.start !== 1) list.start = block.start;   // liste reprise après un paragraphe
        block.items.forEach(function (item) {
          var li = doc.createElement("li");
          appendInline(doc, li, item);
          list.appendChild(li);
        });
        fragment.appendChild(list);
        return;
      }
      var el = doc.createElement(block.type === "h" ? "h4" : "p");
      block.lines.forEach(function (line, i) {
        if (i) el.appendChild(doc.createElement("br"));
        appendInline(doc, el, line);
      });
      fragment.appendChild(el);
    });
    return fragment;
  }

  var api = { parse: parse, inline: inline, render: render };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.DressMeMarkdown = api;
})(typeof window !== "undefined" ? window : this);

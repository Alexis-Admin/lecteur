/* Lecteur — interface (phase 1 : bibliothèque, import, lecture du texte, aperçu et corrections) */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const echap = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let api = null;
const etat = {
  infos: null, reglages: {}, livres: [], livre: null, section: null, mode: "mixte",
  ap: { page: null, piste: "texte", lu: false, douteux: [], autoTout: false, ouverts: new Set() },
  imp: { type: "pdf", fichier: null, images: [], profil: "bible_etude", enCours: false },
};

// ---------- utilitaires ----------
function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("on");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("on"), 2200);
}
function sauverReglages(r) {
  Object.assign(etat.reglages, r);
  api.enregistrer_reglages(r);
}
function blocs(section, piste) { return section.blocs.filter((b) => !piste || b.piste === piste); }
function aDesNotes(livre) { return livre.sections.some((s) => s.blocs.some((b) => b.piste === "notes")); }

function listeDeLecture(section, mode) {
  const texte = blocs(section, "texte"), notes = blocs(section, "notes");
  if (mode === "texte" || !notes.length) return mode === "notes" ? notes : texte;
  if (mode === "notes") return notes;
  let restantes = [...notes];
  const res = [];
  for (const b of texte) {
    res.push(b);
    if (b.genre === "verset") {
      const ici = restantes.filter((n) => n.ch === b.ch && n.v === b.v);
      res.push(...ici);
      restantes = restantes.filter((n) => !ici.includes(n));
    }
  }
  return res.concat(restantes);
}

// ---------- thème ----------
function appliquerTheme(theme) {
  document.body.dataset.theme = theme;
  $("#b-theme").title = theme === "nuit" ? "Mode jour (Ctrl+J)" : "Mode nuit (Ctrl+J)";
  $("#b-theme").setAttribute("aria-label", theme === "nuit" ? "Mode jour" : "Mode nuit");
}
function basculerTheme() {
  const t = document.body.dataset.theme === "nuit" ? "jour" : "nuit";
  appliquerTheme(t);
  sauverReglages({ theme: t });
}

// ---------- bibliothèque ----------
async function chargerLivres() {
  etat.livres = await api.liste_livres();
  const ul = $("#livres");
  if (!etat.livres.length) {
    ul.innerHTML = `<span class="vide-liste">Aucun livre pour l'instant.</span>`;
    return;
  }
  ul.innerHTML = etat.livres.map((l) => `
    <button class="sec ${etat.livre && etat.livre.id === l.id ? "actif" : ""}" data-id="${l.id}" title="${echap(l.titre)} — clic droit : options">
      <span class="n"><svg viewBox="0 0 24 24"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20V3H6.5A2.5 2.5 0 0 0 4 5.5z"/></svg></span>
      <span class="t">${echap(l.titre)}</span><span class="d mono">${{ texte: "texte", web: "web" }[l.type] || l.pages + " p."}</span></button>`).join("");
  $$("#livres .sec").forEach((b) => {
    b.onclick = () => ouvrirLivre(b.dataset.id);
    b.oncontextmenu = (e) => { e.preventDefault(); menuLivre(b); };
  });
}

function menuLivre(bouton) {
  // Menu simple : un second clic sur « Mettre à la corbeille » confirme.
  const id = bouton.dataset.id;
  const t = bouton.querySelector(".t");
  const ancien = t.textContent;
  t.textContent = "Mettre à la corbeille ? (clic = oui)";
  bouton.classList.add("actif");
  const annuler = () => { t.textContent = ancien; chargerLivres(); };
  bouton.onclick = async () => {
    await api.supprimer(id);
    if (etat.livre && etat.livre.id === id) { etat.livre = null; afficherVue("accueil"); $("#carte-livre").hidden = true; $("#sections").innerHTML = ""; $("#lab-sections").hidden = true; }
    toast("Livre mis à la corbeille Windows (récupérable).");
    chargerLivres();
  };
  setTimeout(() => document.addEventListener("click", function f(e) { if (!bouton.contains(e.target)) { annuler(); } document.removeEventListener("click", f); }), 0);
}

async function ouvrirLivre(id, vue = "lecture") {
  try {
    etat.livre = await api.livre(id);
  } catch (e) {
    toast("Impossible d'ouvrir ce livre.");
    return;
  }
  sauverReglages({ dernier_livre: id });
  $("#audio").pause();
  etat.audio.chargee = null;
  etat.audio.e = null;
  const l = etat.livre;
  $("#carte-livre").hidden = false;
  $("#livre-titre").textContent = l.titre;
  const nomProfil = (etat.infos.profils.find((p) => p.id === l.profil) || {}).nom
    || { texte: "Texte collé", web: "Page web", images: "Captures" }[l.meta.type] || "";
  $("#livre-sous").textContent = `${nomProfil}${aDesNotes(l) ? " · texte + notes" : ""}`;
  const pl = (n, mot) => `${n} ${mot}${n > 1 ? "s" : ""}`;
  $("#livre-info").textContent = `${l.pages.length ? pl(l.pages.length, l.meta.type === "images" ? "image" : "page") + " · " : ""}${pl(l.sections.length, "section")}`;
  $("#livre-progres").style.width = "0%";
  $("#b-apercu").disabled = false;
  $("#b-usb").disabled = false;
  $("#b-usb").title = "Copier les MP3 sur une clé USB";
  $("#modes").hidden = !aDesNotes(l);
  // Reprise : la section de la dernière écoute d'abord, sinon la dernière section regardée.
  const pos = (etat.reglages.positions || {})[id];
  const memo = (etat.reglages.sections || {})[id];
  etat.section = l.sections.find((s) => pos && s.id === pos.section) || l.sections.find((s) => s.id === memo) || l.sections[0] || null;
  if (pos && aDesNotes(l) && pos.mode) etat.mode = pos.mode;
  etat.suivi.durees = null;
  dessinerSections();
  chargerLivres();
  if (vue === "apercu") ouvrirApercu(); else afficherLecture();
  await majAudio();
  if (vue !== "apercu" && sectionPrete()) chargerAudioSection(false);
  chargerDurees();
}

function dessinerSections() {
  const l = etat.livre;
  $("#lab-sections").hidden = !l.sections.length;
  const ecoutees = new Set((etat.reglages.ecoutees || {})[l.id] || []);
  const coche = '<svg viewBox="0 0 24 24" aria-label="Écoutée" style="width:14px;height:14px;stroke-width:2.5"><path d="M5 12l5 5 9-10"/></svg>';
  $("#sections").innerHTML = l.sections.map((s, i) => `
    <button class="sec ${etat.section && s.id === etat.section.id ? "actif" : ""} ${ecoutees.has(s.id) ? "fait" : ""}" data-id="${s.id}" title="${echap((s.ref ? s.ref + " · " : "") + s.titre)}${ecoutees.has(s.id) ? " (écoutée)" : ""}">
      <span class="n mono">${ecoutees.has(s.id) ? coche : String(i + 1).padStart(2, "0")}</span>
      <span class="t">${echap(s.ref ? s.ref + " · " + s.titre : s.titre)}</span></button>`).join("");
  $$("#sections .sec").forEach((b) => (b.onclick = () => choisirSection(b.dataset.id)));
  const actif = $("#sections .sec.actif");
  if (actif) actif.scrollIntoView({ block: "nearest" });  // la section en cours reste visible (livres de 50+ sections)
}

function choisirSection(id) {
  sauverPosition();
  etat.section = etat.livre.sections.find((s) => s.id === id);
  const memo = { ...(etat.reglages.sections || {}) };
  memo[etat.livre.id] = id;
  sauverReglages({ sections: memo });
  dessinerSections();
  if (!$("#vue-apercu").hidden) {
    const b = etat.section.blocs.find((x) => x.page);
    if (b) allerPage(b.page);
  } else afficherLecture();
}

// ---------- vues ----------
function afficherVue(nom) {
  for (const v of ["accueil", "lecture", "apercu"]) $(`#vue-${v}`).hidden = v !== nom;
}

function afficherLecture() {
  afficherVue("lecture");
  const l = etat.livre, s = etat.section;
  if (!s) { $("#page-lecture").innerHTML = `<p>Ce livre est vide.</p>`; return; }
  const mode = aDesNotes(l) ? etat.mode : "texte";
  $$("#modes button").forEach((b) => b.classList.toggle("on", b.dataset.mode === mode));
  $("#fil").innerHTML = `${echap(l.titre)} › <b>${echap(s.ref ? s.ref + " · " : "")}${echap(s.titre)}</b>`;
  const idx = l.sections.indexOf(s);
  // Chaque bloc lu à voix haute est un <span class="lu-bloc" data-id> : le surlignage s'y accroche.
  // (Pas « .bt » : ce nom sert déjà à l'en-tête des boîtes.)
  const bt = (b, cls = "") => `<span class="lu-bloc ${cls}" data-id="${b.id}">${echap(b.texte)}</span>`;
  let html = "";
  s.blocs.filter((b) => b.genre === "partie").forEach((p) => (html += `<p class="partie">${bt(p)}</p>`));
  const titre = s.blocs.find((b) => b.genre === "titre");
  html += `<h2>${titre ? bt(titre) : echap(s.titre)}</h2><p class="ref">${echap(s.ref || "")}${s.ref ? " · " : ""}section ${idx + 1} sur ${l.sections.length}</p>`;
  for (const b of listeDeLecture(s, mode)) {
    if (b.genre === "titre" || b.genre === "partie") continue;
    if (b.piste === "notes") {
      const tag = b.genre === "encadre" ? "Encadré" : (b.ref || "Note");
      html += `<div class="note"><span class="tag">${echap(tag)}</span>${bt(b)}</div>`;
    } else if (b.genre === "verset") {
      html += `<p><span class="v">${b.v}</span>${bt(b)}</p>`;
    } else {
      html += `<p>${bt(b)}</p>`;
    }
  }
  $("#page-lecture").innerHTML = html;
  $("#zone-lecture").scrollTop = 0;
  etat.suivi.courant = null;
  etat.suivi.mot = -1;
  if (etat.audio.e && !etat.audio.e.en_cours && sectionPrete()) chargerAudioSection(false);
  else dessinerBarreAudio();
}

// ---------- aperçu ----------
async function ouvrirApercu() {
  afficherVue("apercu");
  const l = etat.livre;
  $("#ap-titre").textContent = l.titre;
  const memo = (etat.reglages.pages_apercu || {})[l.id];
  const liste = pagesApercu();
  etat.ap.page = liste.includes(memo) ? memo
    : sansPages() ? l.sections.indexOf(etat.section) + 1 || 1
    : (etat.section && (etat.section.blocs.find((b) => b.page) || {}).page) || liste[0];
  $(".c-scan h3").textContent = sansPages() ? "Source" : etat.livre.meta.type === "images" ? "Capture" : "Page scannée";
  $$("#pistes button").forEach((b) => b.classList.toggle("on", b.dataset.piste === etat.ap.piste));
  $("#pistes").hidden = !aDesNotes(l);
  dessinerAuto();
  api.etat_audio(l.id).then((e) => {
    const b = $("#b-etape-voix");
    b.classList.add("pret");
    b.lastChild.textContent = e.total && e.fait === e.total ? "Écouter ›" : e.fait ? "Continuer l'audio ›" : "Créer l'audio ›";
  });
  await chargerDouteux();
  allerPage(etat.ap.page);
}

async function chargerDouteux() {
  $("#liste-douteux").innerHTML = `<div class="chargement">Recherche des mots à vérifier…</div>`;
  etat.ap.douteux = await api.douteux(etat.livre.id);
  etat.ap.total0 = etat.ap.douteux.length;
  etat.ap.decoches = new Set();
  dessinerDouteux();
}

// Livre sans pages (texte collé, page web) : l'aperçu avance section par section.
function sansPages() { return !etat.livre.pages.length; }
function pagesApercu() { return sansPages() ? etat.livre.sections.map((_, i) => i + 1) : etat.livre.pages; }

async function allerPage(n) {
  const l = etat.livre;
  const liste = pagesApercu();
  etat.ap.page = n;
  const i = liste.indexOf(n);
  $("#p-num").textContent = sansPages() ? `section ${i + 1}/${liste.length}`
    : `${l.meta.type === "images" ? "image" : "p."} ${n} · ${i + 1}/${liste.length}`;
  $("#p-prec").disabled = i <= 0;
  $("#p-suiv").disabled = i >= liste.length - 1;
  const memo = { ...(etat.reglages.pages_apercu || {}) };
  memo[l.id] = n;
  sauverReglages({ pages_apercu: memo });
  dessinerTexte();
  $("#scan").innerHTML = `<div class="chargement">Chargement de la page…</div>`;
  const r = await api.page(l.id, n, 900);
  if (etat.ap.page !== n) return;
  $(".c-scan .leg").hidden = !!r.sans_page;
  if (r.sans_page) {
    const src = /^https?:/.test(r.source) ? `<a href="${echap(r.source)}" target="_blank" rel="noopener">${echap(r.source)}</a>` : echap(r.source);
    $("#scan").innerHTML = `<div class="source-info"><b>${l.meta.type === "web" ? "Page web" : "Texte collé"}</b>${src}
      <span>${l.sections.length} sections · ${l.sections.reduce((t, s) => t + s.blocs.reduce((u, b) => u + b.texte.split(/\s+/).length, 0), 0).toLocaleString("fr-CA")} mots</span>
      <span>Pas de page scannée : les flèches passent d'une section à l'autre.</span></div>`;
    return;
  }
  if (r.erreur) { $("#scan").innerHTML = `<div class="chargement">${echap(r.erreur)}</div>`; return; }
  const zones = r.zones.map((z) => {
    const g = ["bible", "notes", "encadre", "ignore"].includes(z.genre) ? z.genre : "ignore";
    const st = `left:${(z.x0 / r.largeur) * 100}%;top:${(z.y0 / r.hauteur) * 100}%;width:${((z.x1 - z.x0) / r.largeur) * 100}%;height:${((z.y1 - z.y0) / r.hauteur) * 100}%`;
    return `<div class="zonebox z-${g}" style="${st}"></div>`;
  }).join("");
  $("#scan").innerHTML = `<div style="position:relative"><img src="${r.image}" alt="Page ${n} du PDF">${zones}</div>`;
}

const RE_REF = /(?:\b[123]\s?)?(?:[A-ZÉ][a-zéèëô]{0,3})\.?\s?\d{1,3}\.\d{1,3}[a-c]?(?:\s?[-–]\s?\d{1,3}(?:\.\d{1,3})?)?(?:ss|s)?\b|\(\d{1,3}\.\d{1,3}[a-c]?(?:[-–]\d{1,3})?(?:ss)?\)/g;
const RE_MOT = /[\wÀ-ÿ’'\-]+/g;

function decorer(texte, page) {
  const douteux = new Set(etat.ap.douteux.map((d) => d.mot));
  const auto = new Map();
  for (const c of etat.livre.corrections) {
    if (c.page === page && c.apres !== "∅" && c.apres.length > 1) auto.set(c.apres.replace(/[.,;:»«]+$/, ""), c.avant);
  }
  // 1. Références
  const morceaux = [];
  let i = 0;
  for (const m of texte.matchAll(RE_REF)) {
    if (m.index > i) morceaux.push({ t: texte.slice(i, m.index) });
    morceaux.push({ t: m[0], ref: true });
    i = m.index + m[0].length;
  }
  if (i < texte.length) morceaux.push({ t: texte.slice(i) });
  // 2. Mots douteux et corrections automatiques
  return morceaux.map((p) => {
    if (p.ref) return `<span class="lire-ref" data-ref="${echap(p.t)}">${echap(p.t)}</span>`;
    let out = "", j = 0;
    for (const m of p.t.matchAll(RE_MOT)) {
      out += echap(p.t.slice(j, m.index));
      const mot = m[0];
      if (douteux.has(mot)) out += `<mark class="douteux" title="À vérifier">${echap(mot)}</mark>`;
      else if (auto.has(mot)) out += `<span class="auto" title="Corrigé : « ${echap(auto.get(mot))} » → « ${echap(mot)} »">${echap(mot)}</span>`;
      else out += echap(mot);
      j = m.index + mot.length;
    }
    return out + echap(p.t.slice(j));
  }).join("");
}

async function dessinerTexte() {
  const l = etat.livre, n = etat.ap.page, piste = aDesNotes(l) ? etat.ap.piste : "texte";
  const liste = sansPages()
    ? (l.sections[n - 1] || { blocs: [] }).blocs.filter((b) => b.piste === piste)
    : l.sections.flatMap((s) => s.blocs.filter((b) => b.page === n && b.piste === piste));
  const zone = $("#ap-texte");
  if (!liste.length) {
    zone.innerHTML = `<p class="petit">Rien sur cette page pour la piste « ${piste === "notes" ? "Notes" : "Texte"} ».</p>`;
    return;
  }
  if (etat.ap.lu) {
    const lus = await api.blocs_lus(l.id, liste.map((b) => b.id));
    zone.innerHTML = liste.map((b, i) => `<p class="bloc lu">${echap(lus[i])}</p>`).join("");
    return;
  }
  zone.innerHTML = liste.map((b) => {
    const tag = b.piste === "notes" ? `<span class="tag" contenteditable="false">${echap(b.genre === "encadre" ? "Encadré" : (b.ref || "Note"))}</span>` : "";
    const num = b.genre === "verset" ? `<span class="v" contenteditable="false">${b.v}</span>` : "";
    return `<div class="bloc g-${b.genre}" data-id="${b.id}">${tag}${num}<span class="corps" contenteditable="true" spellcheck="false">${decorer(b.texte, n)}</span></div>`;
  }).join("");
  $$("#ap-texte .corps").forEach((el) => {
    el.addEventListener("blur", async () => {
      const id = el.parentElement.dataset.id;
      const texte = el.innerText.replace(/\s+/g, " ").trim();
      const b = l.sections.flatMap((s) => s.blocs).find((x) => x.id === id);
      if (!b || b.texte === texte) return;
      await api.modifier_bloc(l.id, id, texte);
      b.texte = texte;
      toast("Correction enregistrée.");
    });
    el.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); el.blur(); } });
  });
  $$("#ap-texte .lire-ref").forEach((el) => el.addEventListener("mouseenter", async () => {
    if (el.title) return;
    el.title = "Se lit : « " + (await api.prononciation(el.dataset.ref, l.refs_nues, "")) + " »";
  }, { once: true }));
}

// Panneau « Révision » : 1. changements sûrs (cochés d'office, un seul bouton) ;
// 2. à décider (un choix par mot) ; 3. déjà corrigé automatiquement (pour information, replié).
const RAISONS = {
  "inconnu (début de phrase)": "nom ou mot inconnu",
  "mot inconnu du dictionnaire": "absent du dictionnaire",
  "chiffres et lettres mélangés": "chiffres et lettres mélangés",
  "majuscule au milieu du mot": "majuscule au milieu du mot",
};

function lieu(ex) {
  return `data-page="${ex.page || ""}" data-section="${ex.section || ""}" data-piste="${ex.piste || ""}"`;
}

function allerA(el) {
  if (el.dataset.piste && aDesNotes(etat.livre)) choisirPiste(el.dataset.piste, false);
  if (sansPages()) allerPage(etat.livre.sections.findIndex((s) => s.id === el.dataset.section) + 1 || 1);
  else if (el.dataset.page) allerPage(Number(el.dataset.page));
}

function dessinerDouteux() {
  const liste = etat.ap.douteux;
  const total = Math.max(etat.ap.total0 || 0, liste.length);
  const regles = total - liste.length;
  $("#rev-etat").textContent = total ? `${regles} sur ${total} réglé${regles > 1 ? "s" : ""}` : "";
  $("#rev-barre").style.width = total ? `${(regles / total) * 100}%` : "100%";
  const fini = !liste.length;
  $("#et-texte").classList.toggle("fait", fini);
  $("#et-texte .r").textContent = fini ? "✓" : "2";
  const zone = $("#liste-douteux");
  if (fini) {
    zone.innerHTML = `<div class="tout-bon"><svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></svg><span>Tout est vérifié.<br><small>Tu peux encore modifier le texte au milieu.</small></span></div>
      <button class="prim rev-suite" id="rev-suite">${echap($("#b-etape-voix").lastChild.textContent.replace("›", "").trim() || "Créer l'audio")} ›</button>`;
    $("#rev-suite").onclick = () => $("#b-etape-voix").click();
    return;
  }
  const surs = liste.map((d, i) => ({ d, i })).filter((x) => x.d.sur && x.d.suggestions.length);
  const autres = liste.map((d, i) => ({ d, i })).filter((x) => !(x.d.sur && x.d.suggestions.length));
  const coches = surs.filter((x) => !etat.ap.decoches.has(x.d.mot)).length;
  let html = "";
  if (surs.length) {
    html += `<section class="rev-groupe rev-sur">
      <div class="rev-tete"><span class="lab-c">Changements sûrs · ${surs.length}</span>
        <button class="lien" id="rev-bascule">${coches ? "Tout décocher" : "Tout cocher"}</button></div>
      <p class="aide">Des erreurs de scan évidentes (accent manquant, lettre mal lue, « à » collé). Décoche ce qui ne te convient pas.</p>
      ${surs.map(({ d, i }) => {
        const ex = d.exemples[0] || {};
        return `<label class="ch">
          <input type="checkbox" data-sur="${echap(d.mot)}" ${etat.ap.decoches.has(d.mot) ? "" : "checked"}>
          <span class="ch-corps">
            <span class="ch-l"><span class="av">${echap(d.mot)}</span><span class="fl">›</span><span class="ap">${echap(d.suggestions[0])}</span>
              <span class="ou" ${lieu(ex)} title="Voir dans la page">${ex.page ? "p. " + ex.page : "voir"}${d.nb > 1 ? " · " + d.nb + " fois" : ""}</span></span>
            <span class="ch-ctx">${ex.avant.length > 34 ? "…" : ""}${echap(ex.avant.slice(-34))}<b>${echap(d.mot)}</b>${echap(ex.apres.slice(0, 34))}${ex.apres.length > 34 ? "…" : ""}</span>
          </span></label>`;
      }).join("")}
      <button class="prim" id="rev-appliquer" ${coches ? "" : "disabled"}>Appliquer ${coches > 1 ? "les " + coches + " changements" : coches ? "ce changement" : ""}</button>
    </section>`;
  }
  if (autres.length) {
    html += `<section class="rev-groupe">
      <div class="rev-tete"><span class="lab-c">À décider · ${autres.length}</span></div>
      <p class="aide">Clique sur la bonne forme. Si le mot est déjà bon (un nom propre, par exemple), choisis « C'est bon ».</p>
      ${autres.slice(0, 80).map(({ d, i }) => {
        const ex = d.exemples[0] || {};
        const sug = (d.suggestions.length ? '<span class="rev-choix">Remplacer par</span>' : "") + d.suggestions.map((s) => `<button class="pil" data-i="${i}" data-rempl="${echap(s)}" title="Remplacer « ${echap(d.mot)} » par « ${echap(s)} » partout">${echap(s)}</button>`).join("");
        return `<div class="item" data-i="${i}">
          <span class="ctx" ${lieu(ex)} title="Voir dans la page">${echap(ex.avant)}<b>${echap(d.mot)}</b>${echap(ex.apres)}</span>
          <span class="meta">${ex.page ? "p. " + ex.page + " · " : ""}${d.nb > 1 ? d.nb + " fois · " : ""}${echap(RAISONS[d.raison] || d.raison)}</span>
          ${sug ? `<div class="acts">${sug}</div>` : ""}
          <div class="acts"><button class="pil" data-garder="${i}" title="Le mot est correct : le garder tel quel et ne plus le signaler">C'est bon</button><button class="pil" data-corriger="${i}" title="Taper la bonne forme moi-même">Écrire…</button></div>
        </div>`;
      }).join("")}
      ${autres.length > 80 ? `<p class="petit">… et ${autres.length - 80} autres. Règle ceux-ci d'abord.</p>` : ""}
    </section>`;
  }
  zone.innerHTML = html;

  $$("#liste-douteux .ctx, #liste-douteux .ou").forEach((el) => (el.onclick = (e) => { e.preventDefault(); allerA(el); }));
  $$("#liste-douteux [data-sur]").forEach((el) => (el.onchange = () => {
    if (el.checked) etat.ap.decoches.delete(el.dataset.sur); else etat.ap.decoches.add(el.dataset.sur);
    dessinerDouteux();
  }));
  const bascule = $("#rev-bascule");
  if (bascule) bascule.onclick = () => {
    if (coches) surs.forEach((x) => etat.ap.decoches.add(x.d.mot)); else etat.ap.decoches.clear();
    dessinerDouteux();
  };
  const appliquer = $("#rev-appliquer");
  if (appliquer) appliquer.onclick = async () => {
    appliquer.disabled = true;
    const paires = surs.filter((x) => !etat.ap.decoches.has(x.d.mot)).map((x) => [x.d.mot, x.d.suggestions[0]]);
    const retenir = $("#retenir").checked;
    const n = await api.remplacer_plusieurs(etat.livre.id, paires, retenir);
    const faits = new Set(paires.map((p) => p[0]));
    await rechargerLivre();
    etat.ap.douteux = etat.ap.douteux.filter((d) => !faits.has(d.mot));
    dessinerDouteux(); dessinerTexte(); dessinerSections();
    toast(`${paires.length} changement${paires.length > 1 ? "s" : ""} appliqué${paires.length > 1 ? "s" : ""} (${n} endroit${n > 1 ? "s" : ""})${retenir ? " · retenus pour les prochains livres" : ""}.`);
  };
  $$("#liste-douteux [data-rempl]").forEach((el) => (el.onclick = () => remplacer(liste[el.dataset.i].mot, el.dataset.rempl)));
  $$("#liste-douteux [data-garder]").forEach((el) => (el.onclick = async () => {
    const mot = liste[el.dataset.garder].mot;
    await api.ignorer(mot);
    etat.ap.douteux = etat.ap.douteux.filter((d) => d.mot !== mot);
    dessinerDouteux(); dessinerTexte();
    toast(`« ${mot} » gardé tel quel : il ne sera plus signalé.`);
  }));
  $$("#liste-douteux [data-corriger]").forEach((el) => (el.onclick = () => {
    const i = Number(el.dataset.corriger), d = liste[i];
    const acts = el.parentElement;
    acts.innerHTML = `<input type="text" value="${echap(d.mot)}" aria-label="Remplacer par"><button class="pil ok">Remplacer partout</button><button class="pil">Annuler</button>`;
    const inp = acts.querySelector("input");
    inp.focus(); inp.select();
    const go = () => { const v = inp.value.trim(); if (v && v !== d.mot) remplacer(d.mot, v); };
    acts.querySelector(".ok").onclick = go;
    acts.querySelectorAll(".pil")[1].onclick = () => dessinerDouteux();
    inp.onkeydown = (e) => { if (e.key === "Enter") go(); if (e.key === "Escape") { e.stopPropagation(); dessinerDouteux(); } };
  }));
}

async function rechargerLivre() {
  etat.livre = await api.livre(etat.livre.id);
  etat.section = etat.livre.sections.find((s) => etat.section && s.id === etat.section.id) || etat.livre.sections[0];
}

async function remplacer(avant, apres) {
  const retenir = $("#retenir").checked;
  const n = await api.remplacer(etat.livre.id, avant, apres, retenir);
  await rechargerLivre();
  etat.ap.douteux = etat.ap.douteux.filter((d) => d.mot !== avant);
  dessinerDouteux(); dessinerTexte(); dessinerSections();
  toast(`« ${avant} » → « ${apres} » : ${n} remplacement${n > 1 ? "s" : ""}${retenir ? " · retenu pour les prochains livres" : ""}.`);
}

// Corrections automatiques, regroupées par sorte.
function sorteAuto(c) {
  if (/\S- \S/.test(c.avant)) return "Mots coupés recollés";
  if (/^\*?(II|11|Il|il|lI|1l)$/.test(c.avant.replace(/^\*/, "")) && /^[Ii]l$/.test(c.apres)) return "« II » lu comme « Il »";
  if (c.apres === "∅" || c.apres.replace(/[^\wÀ-ÿ]/g, "") === c.avant.replace(/[^\wÀ-ÿ]/g, "")) return "Taches et signes parasites retirés";
  if (/\d/.test(c.apres)) return "Références bibliques";
  return "Lettres corrigées";
}

function dessinerAuto() {
  const groupes = new Map();
  let total = 0;
  for (const c of etat.livre.corrections) {
    if (c.apres === "∅" && c.avant.length <= 1) continue;
    total++;
    const g = sorteAuto(c);
    if (!groupes.has(g)) groupes.set(g, new Map());
    const cle = c.avant + "→" + c.apres;
    const m = groupes.get(g);
    m.set(cle, { ...c, nb: (m.get(cle)?.nb || 0) + 1 });
  }
  $("#lab-auto").textContent = `Déjà corrigé automatiquement · ${total}`;
  $("#auto-bloc").hidden = !total;
  $("#liste-auto").innerHTML = [...groupes.entries()].map(([g, m]) => `<div class="auto-g">
      <span class="auto-titre">${echap(g)} <span class="mono">${[...m.values()].reduce((t, c) => t + c.nb, 0)}</span></span>
      <div class="auto-l">${[...m.values()].map((c) => `<span class="av" data-page="${c.page || ""}" title="Voir la page ${c.page}">${echap(c.avant)}</span><span class="fl">›</span><span class="ap" data-page="${c.page || ""}" title="p. ${c.page}${c.nb > 1 ? " · " + c.nb + " fois" : ""}">${echap(c.apres === "∅" ? "(retiré)" : c.apres)}</span>`).join("")}</div>
    </div>`).join("");
  $$("#liste-auto [data-page]").forEach((el) => (el.onclick = () => { if (el.dataset.page && !sansPages()) allerPage(Number(el.dataset.page)); }));
}

function choisirPiste(piste, redessiner = true) {
  etat.ap.piste = piste;
  $$("#pistes button").forEach((b) => b.classList.toggle("on", b.dataset.piste === piste));
  if (redessiner) dessinerTexte();
}

// ---------- import ----------
const PROFILS_AIDE = {
  bible_etude: { aide: "Texte en haut, notes en 2 colonnes en bas", mini: '<i style="left:12%;top:10%;width:76%;height:44%;background:#0A84FF33;border:1px solid #0A84FF"></i><i style="left:8%;top:62%;width:40%;height:30%;background:#C9A46A44;border:1px solid #B08D57"></i><i style="left:52%;top:62%;width:40%;height:30%;background:#C9A46A44;border:1px solid #B08D57"></i>' },
  deux_colonnes: { aide: "Colonne de gauche, puis de droite", mini: '<i style="left:8%;top:12%;width:40%;height:78%;background:#0A84FF33;border:1px solid #0A84FF"></i><i style="left:52%;top:12%;width:40%;height:78%;background:#0A84FF33;border:1px solid #0A84FF"></i>' },
  simple: { aide: "Une colonne, page après page", mini: '<i style="left:14%;top:12%;width:72%;height:78%;background:#0A84FF33;border:1px solid #0A84FF"></i>' },
};

function ouvrirImport(type = etat.reglages.type_import || "pdf", contenu = null) {
  if (etat.imp.enCours) return;
  etat.imp.fichier = null;
  etat.imp.images = [];
  $("#imp-nom").textContent = "Choisir un PDF…";
  $("#imp-details").textContent = "PDF scanné (CZUR) ou PDF normal";
  $("#imp-titre-livre").value = "";
  $("#imp-pages").value = "";
  $("#imp-texte").value = "";
  $("#imp-url").value = "";
  $("#imp-erreur").hidden = true;
  $("#imp-progres").hidden = true;
  $("#imp-resume").textContent = "";
  $("#import").hidden = false;
  choisirOnglet(type);
  if (contenu && contenu.image) ajouterImage(contenu.image);
  if (contenu && contenu.texte) { $("#imp-texte").value = contenu.texte; majImport(); }
}
function fermerImport() { if (!etat.imp.enCours) $("#import").hidden = true; }

function choisirOnglet(type) {
  etat.imp.type = type;
  sauverReglages({ type_import: type });
  $$("#imp-onglets button").forEach((b) => b.classList.toggle("on", b.dataset.type === type));
  $$(".panneau").forEach((p) => (p.hidden = p.dataset.panneau !== type));
  $("#imp-bloc-profils").hidden = !["pdf", "images"].includes(type);
  $("#imp-bloc-pages").hidden = type !== "pdf";
  if (type === "images" && !["simple", "deux_colonnes"].includes(etat.imp.profil)) etat.imp.profil = "simple";
  if (type === "images") api.ocr_disponible().then((ok) => ($("#imp-ocr-absent").hidden = ok));
  dessinerProfils();
  majImport();
  const premierChamp = { pdf: "#imp-fichier", images: "#imp-images", texte: "#imp-texte", web: "#imp-url" }[type];
  if (premierChamp) $(premierChamp).focus();
}

function majImport() {
  const t = etat.imp.type;
  const pret = t === "pdf" ? !!etat.imp.fichier
    : t === "images" ? etat.imp.images.length > 0
    : t === "texte" ? $("#imp-texte").value.trim().length > 0
    : /\S+\.\S+/.test($("#imp-url").value.trim());
  $("#imp-go").disabled = !pret || etat.imp.enCours;
  $("#imp-resume").textContent = !pret ? ""
    : t === "images" ? `${etat.imp.images.length} image${etat.imp.images.length > 1 ? "s" : ""} · une page chacune`
    : t === "texte" ? `${$("#imp-texte").value.trim().split(/\s+/).length.toLocaleString("fr-CA")} mots`
    : "Prêt à importer.";
}

function ajouterImage(source) {
  etat.imp.images.push(source);
  dessinerVignettes();
  majImport();
}

function dessinerVignettes() {
  $("#imp-vignettes").innerHTML = etat.imp.images.map((im, i) => `
    <div class="vignette" title="${echap(im.nom)}">
      ${im.donnees ? `<img src="${im.donnees}" alt="">` : ""}
      <span class="num">${i + 1}</span><button class="x2" data-i="${i}" aria-label="Retirer">×</button>
      <span class="nom">${echap(im.nom)}</span></div>`).join("");
  $$("#imp-vignettes .x2").forEach((b) => (b.onclick = () => { etat.imp.images.splice(Number(b.dataset.i), 1); dessinerVignettes(); majImport(); }));
}

async function choisirImages() {
  const liste = await api.choisir_images();
  liste.forEach((im) => etat.imp.images.push(im));
  dessinerVignettes();
  majImport();
  if (liste.length && !$("#imp-titre-livre").value) $("#imp-titre-livre").value = liste[0].nom.replace(/\.[^.]+$/, "");
}

function lireCollage(e) {
  // Ctrl+V : une image collée devient une capture ; un texte collé hors d'un champ ouvre l'onglet Texte.
  const items = [...(e.clipboardData?.items || [])];
  const image = items.find((i) => i.type.startsWith("image/"));
  const dansChamp = e.target.isContentEditable || ["INPUT", "TEXTAREA"].includes(e.target.tagName);
  if (image) {
    e.preventDefault();
    const lecteur = new FileReader();
    lecteur.onload = () => {
      const src = { donnees: lecteur.result, nom: `Capture ${new Date().toLocaleTimeString("fr-CA")}` };
      if ($("#import").hidden) ouvrirImport("images", { image: src });
      else { if (etat.imp.type !== "images") choisirOnglet("images"); ajouterImage(src); }
    };
    lecteur.readAsDataURL(image.getAsFile());
  } else if (!dansChamp && $("#import").hidden) {
    const texte = e.clipboardData?.getData("text/plain") || "";
    if (/^https?:\/\/\S+$/.test(texte.trim())) { e.preventDefault(); ouvrirImport("web"); $("#imp-url").value = texte.trim(); majImport(); }
    else if (texte.trim().split(/\s+/).length > 20) { e.preventDefault(); ouvrirImport("texte", { texte }); }
  }
}

function dessinerProfils() {
  const permis = etat.imp.type === "images" ? ["simple", "deux_colonnes"] : etat.infos.profils.map((p) => p.id);
  $("#imp-profils").innerHTML = etat.infos.profils.filter((p) => permis.includes(p.id)).map((p) => `
    <button class="profil ${p.id === etat.imp.profil ? "on" : ""}" data-id="${p.id}">
      <span class="mini">${PROFILS_AIDE[p.id].mini}</span><b>${echap(p.nom)}</b><span>${PROFILS_AIDE[p.id].aide}</span></button>`).join("");
  $$("#imp-profils .profil").forEach((b) => (b.onclick = () => { etat.imp.profil = b.dataset.id; dessinerProfils(); }));
}

async function choisirFichier() {
  const f = await api.choisir_pdf();
  if (!f) return;
  etat.imp.fichier = f;
  $("#imp-nom").textContent = f.nom;
  $("#imp-details").textContent = `${f.pages} pages${f.a_du_texte ? "" : " · ⚠ aucun texte trouvé : ce PDF n'a pas été passé à l'OCR"}`;
  if (!$("#imp-titre-livre").value) $("#imp-titre-livre").value = f.titre;
  const nom = f.nom.toLowerCase();
  if (/bible|gen[eè]se|exode|psaume|segond/.test(nom)) etat.imp.profil = "bible_etude";
  else if (/commentaire/.test(nom)) etat.imp.profil = "deux_colonnes";
  dessinerProfils();
  majImport();
}

window.progresImport = (i, n, sec) => {
  $("#imp-barre").style.width = `${Math.max(1, Math.floor((i / n) * 100))}%`;
  $("#imp-compte").textContent = `${i} / ${n}`;
  if (i > 3 && i < n) {
    const reste = Math.round((sec / i) * (n - i));
    $("#imp-etape").textContent = `Lecture des pages… environ ${reste < 60 ? reste + " s" : Math.round(reste / 60) + " min"} restantes`;
  } else if (i === n) $("#imp-etape").textContent = "Assemblage des sections et des notes…";
};

async function lancerImport() {
  const t = etat.imp.type, titre = $("#imp-titre-livre").value.trim();
  if ($("#imp-go").disabled) return;
  etat.imp.enCours = true;
  $("#imp-go").disabled = true;
  $("#imp-annuler").disabled = true;
  $("#imp-erreur").hidden = true;
  $("#imp-progres").hidden = false;
  $("#imp-barre").style.width = "1%";
  $("#imp-compte").textContent = "";
  $("#imp-etape").textContent = { pdf: "Lecture des pages…", images: "Reconnaissance du texte des images…",
    texte: "Nettoyage du texte…", web: "Téléchargement de la page…" }[t];
  try {
    const r = t === "pdf" ? await api.importer(etat.imp.fichier.chemin, etat.imp.profil, $("#imp-pages").value, titre)
      : t === "images" ? await api.importer_images(etat.imp.images, etat.imp.profil, titre)
      : t === "texte" ? await api.importer_texte($("#imp-texte").value, titre)
      : await api.importer_url($("#imp-url").value.trim(), titre);
    etat.imp.enCours = false;
    $("#imp-annuler").disabled = false;
    $("#import").hidden = true;
    await chargerLivres();
    await ouvrirLivre(r.id, "apercu");
    toast("Import terminé. Vérifie le texte avant de créer l'audio.");
  } catch (e) {
    etat.imp.enCours = false;
    $("#imp-annuler").disabled = false;
    $("#imp-go").disabled = false;
    $("#imp-progres").hidden = true;
    const msg = String(e && e.message ? e.message : e);
    $("#imp-erreur").textContent = "L'import n'a pas fonctionné : " + msg.replace(/^.*Error: /, "");
    $("#imp-erreur").hidden = false;
  }
}

// ---------- audio (phase 2) ----------
const ICONES = {
  play: '<svg viewBox="0 0 24 24"><path d="M8 5l11 7-11 7z"/></svg>',
  pause: '<svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>',
  prec: '<svg viewBox="0 0 24 24"><path d="M6 5v14M18 6l-9 6 9 6z"/></svg>',
  suiv: '<svg viewBox="0 0 24 24"><path d="M18 5v14M6 6l9 6-9 6z"/></svg>',
};
etat.audio = { e: null, minuterie: null, debut: null, chargee: null, voix: null };
const VITESSES = [0.75, 1, 1.1, 1.25, 1.5, 1.75, 2, 2.5, 3];
const VIT_MIN = 0.75, VIT_MAX = 3, VIT_PAS = 0.05;
function vitTexte(x) { return x.toLocaleString("fr-CA", { minimumFractionDigits: x % 1 ? 2 : 0, maximumFractionDigits: 2 }).replace(/(,\d)0$/, "$1") + "x"; }

// Vitesse par pas de 0,05x (Alexis : de 1,25x à 1,5x, l'écart était trop grand).
function regleVitesse(x) {
  x = Math.round(Math.min(VIT_MAX, Math.max(VIT_MIN, x)) * 100) / 100;
  const a = $("#audio");
  a.playbackRate = x;
  sauverReglages({ vitesse: x });
  dessinerLecteur();
  return x;
}
const fmt = (s) => { s = Math.max(0, Math.floor(s || 0)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : String(m).padStart(2, "0")) + ":" + String(x).padStart(2, "0"); };

async function majAudio() {
  if (!etat.livre) return;
  const id = etat.livre.id;
  const e = await api.etat_audio(id);
  if (!etat.livre || etat.livre.id !== id) return;
  etat.audio.e = e;
  if (e.en_cours) {
    if (!etat.audio.debut) etat.audio.debut = { t: Date.now(), fait: e.fait };
    clearTimeout(etat.audio.minuterie);
    etat.audio.minuterie = setTimeout(majAudio, 1000);
  } else {
    if (etat.audio.debut) { etat.audio.debut = null; toast(e.erreurs.length ? "Création arrêtée : " + e.erreurs[0] : "Audio créé."); }
  }
  dessinerBarreAudio();
}

function sectionPrete() {
  const e = etat.audio.e;
  if (!e || !etat.section) return false;
  const s = e.sections.find((x) => x.id === etat.section.id);
  return s && s.total > 0 && s.fait === s.total;
}

function dessinerBarreAudio() {
  const e = etat.audio.e, b = $("#barre-audio");
  if (!e) { b.innerHTML = ""; return; }
  if (e.en_cours) {
    const pc = e.total ? Math.max(1, Math.floor((e.fait / e.total) * 100)) : 0;
    let reste = "";
    const d = etat.audio.debut;
    if (d && e.fait > d.fait + 2) {
      const sec = ((Date.now() - d.t) / 1000 / (e.fait - d.fait)) * (e.total - e.fait);
      reste = sec < 90 ? `environ ${Math.round(sec)} s` : `environ ${Math.round(sec / 60)} min`;
    }
    b.innerHTML = `<div class="gen"><div class="l1"><span>Création de l'audio… <b>${e.fait.toLocaleString("fr-CA")} / ${e.total.toLocaleString("fr-CA")}</b> morceaux</span><span>${reste}</span></div>
      <div class="rail"><i style="width:${pc}%"></i></div></div>
      <button class="sec3" id="b-pause-gen" title="Arrêter ; tu pourras reprendre où ça s'est arrêté">Pause</button>`;
    $("#b-pause-gen").onclick = async () => { await api.arreter_audio(); toast("Arrêt après les morceaux en cours…"); };
    return;
  }
  if (sectionPrete()) { dessinerLecteur(); return; }
  const fini = e.total && e.fait === e.total;
  const msg = e.autre_en_cours ? "Un autre livre est en train de créer son audio. Attends qu'il finisse."
    : e.fait === 0 ? `L'audio n'est pas encore créé (${e.total.toLocaleString("fr-CA")} morceaux). Vérifie le texte dans <b>Aperçu</b>, puis lance la création.`
    : fini ? "Cette section n'a rien à lire." : `Audio créé à <b>${Math.floor((e.fait / e.total) * 100)} %</b>. Tu peux continuer où ça s'est arrêté.`;
  const err = e.erreurs && e.erreurs.length ? `<br><span style="color:#FFB4A8">${echap(e.erreurs[0])}</span>` : "";
  b.innerHTML = `<span class="lecteur-msg">${msg}${err}</span>
    <button class="prim" id="b-gen" ${e.autre_en_cours || fini ? "disabled" : ""}>${e.fait ? "Continuer la création" : "Créer l'audio"}</button>`;
  const bg = $("#b-gen");
  if (bg) bg.onclick = async () => { await api.generer_audio(etat.livre.id); etat.audio.debut = null; majAudio(); };
}

function dessinerLecteur() {
  const a = $("#audio"), l = etat.livre, i = l.sections.indexOf(etat.section);
  const v = etat.reglages.vitesse || 1;
  $("#barre-audio").innerHTML = `
    <div class="ctl">
      <button class="cb" id="a-prec" aria-label="Section précédente" title="Section précédente (Ctrl+←)" ${i <= 0 ? "disabled" : ""}>${ICONES.prec}</button>
      <button class="cb" id="a-moins" aria-label="Reculer de 15 secondes" title="Reculer de 15 s (←)">−15</button>
      <button class="play" id="a-play" aria-label="Lecture ou pause" title="Lecture / pause (Espace)">${a.paused ? ICONES.play : ICONES.pause}</button>
      <button class="cb" id="a-plus" aria-label="Avancer de 15 secondes" title="Avancer de 15 s (→)">+15</button>
      <button class="cb" id="a-suiv" aria-label="Section suivante" title="Section suivante (Ctrl+→)" ${i >= l.sections.length - 1 ? "disabled" : ""}>${ICONES.suiv}</button>
    </div>
    <div class="temps"><div class="l1"><span class="mono" id="a-t">${fmt(a.currentTime)}</span><span>${i < l.sections.length - 1 ? "Suivante : " + echap(l.sections[i + 1].ref || l.sections[i + 1].titre) : "Fin du livre"}</span><span class="mono" id="a-reste">−${fmt((a.duration || 0) - a.currentTime)}</span></div>
      <div class="rail" id="a-rail" title="Cliquer pour aller à cet endroit"><i id="a-barre" style="width:${a.duration ? (a.currentTime / a.duration) * 100 : 0}%"></i></div></div>
    <div class="vit-g" role="group" aria-label="Vitesse de lecture">
      <button class="cb vit-pas" id="a-vit-moins" aria-label="Moins vite" title="Moins vite : −0,05x ([)" ${v <= VIT_MIN ? "disabled" : ""}>−</button>
      <select class="vit" id="a-vit" aria-label="Vitesse de lecture" title="Vitesse : 0,75x à 3x. − et + changent de 0,05x ([ et ])">
        ${[...new Set([...VITESSES, v])].sort((x, y) => x - y).map((x) => `<option value="${x}" ${x === v ? "selected" : ""}>${vitTexte(x)}</option>`).join("")}</select>
      <button class="cb vit-pas" id="a-vit-plus" aria-label="Plus vite" title="Plus vite : +0,05x (])" ${v >= VIT_MAX ? "disabled" : ""}>+</button>
    </div>`;
  $("#a-play").onclick = basculerLecture;
  $("#a-moins").onclick = () => sauter(-15);
  $("#a-plus").onclick = () => sauter(15);
  $("#a-prec").onclick = () => changerSection(-1, !a.paused);
  $("#a-suiv").onclick = () => changerSection(1, !a.paused);
  $("#a-vit").onchange = (ev) => regleVitesse(Number(ev.target.value));
  $("#a-vit-moins").onclick = () => regleVitesse((etat.reglages.vitesse || 1) - VIT_PAS);
  $("#a-vit-plus").onclick = () => regleVitesse((etat.reglages.vitesse || 1) + VIT_PAS);
  $("#a-rail").onclick = (ev) => { const r = ev.currentTarget.getBoundingClientRect(); if (a.duration) a.currentTime = ((ev.clientX - r.left) / r.width) * a.duration; };
}

async function chargerAudioSection(jouer = false) {
  const l = etat.livre, s = etat.section, a = $("#audio");
  if (!l || !s || !sectionPrete()) return false;
  const mode = aDesNotes(l) ? etat.mode : "texte";
  const cle = `${l.id}|${s.id}|${mode}|${etat.audio.e.voix}`;
  if (etat.audio.chargee !== cle) {
    const r = await api.audio_section(l.id, s.id, mode);
    if (!r.url) { if (r.erreur) toast(r.erreur); return false; }
    etat.audio.chargee = cle;
    // La section suivante est préparée pendant l'écoute : on y passe sans attendre.
    const suiv = l.sections[l.sections.indexOf(s) + 1];
    if (suiv) api.preparer_section(l.id, suiv.id, mode);
    preparerMinutage(r.minutage);
    a.src = r.url;
    a.playbackRate = etat.reglages.vitesse || 1;
    // Reprise : la position retenue pour ce livre et cette section.
    const pos = (etat.reglages.positions || {})[l.id];
    if (pos && pos.section === s.id && pos.mode === mode && pos.t > 1) {
      await new Promise((ok) => { if (a.readyState >= 1) ok(); else a.addEventListener("loadedmetadata", ok, { once: true }); });
      a.currentTime = Math.min(pos.t, (a.duration || pos.t) - 0.5);
    }
    majMediaSession();
  }
  if (jouer) { try { await a.play(); } catch (e) { /* lecture refusée */ } }
  dessinerLecteur();
  majSurlignage(true);
  majProgression();
  return true;
}

async function basculerLecture() {
  const a = $("#audio");
  if (!a.src || etat.audio.chargee === null) { await chargerAudioSection(true); return; }
  if (a.paused) a.play(); else a.pause();
}
function sauter(sec) { const a = $("#audio"); if (a.duration) a.currentTime = Math.min(a.duration, Math.max(0, a.currentTime + sec)); }
async function changerSection(delta, jouer) {
  const l = etat.livre, i = l.sections.indexOf(etat.section) + delta;
  if (i < 0 || i >= l.sections.length) return;
  choisirSection(l.sections[i].id);
  if (sectionPrete()) await chargerAudioSection(jouer);
}

function brancherAudio() {
  const a = $("#audio");
  a.addEventListener("loadedmetadata", () => $("#a-reste") && ($("#a-reste").textContent = "−" + fmt(a.duration - a.currentTime)));
  a.addEventListener("timeupdate", () => {
    if (!$("#a-t")) return;
    $("#a-t").textContent = fmt(a.currentTime);
    $("#a-reste").textContent = "−" + fmt((a.duration || 0) - a.currentTime);
    $("#a-barre").style.width = a.duration ? `${(a.currentTime / a.duration) * 100}%` : "0%";
  });
  a.addEventListener("play", () => { $("#a-play") && ($("#a-play").innerHTML = ICONES.pause); boucleSuivi(); });
  a.addEventListener("pause", () => { $("#a-play") && ($("#a-play").innerHTML = ICONES.play); sauverPosition(); });
  a.addEventListener("seeked", () => { majSurlignage(true); sauverPosition(); });
  a.addEventListener("ended", () => { marquerEcoutee(etat.section.id); changerSection(1, true); });
  window.addEventListener("beforeunload", sauverPosition);
  brancherSuivi();
  $("#b-voix").onclick = (ev) => { ev.stopPropagation(); basculerPopVoix(); };
  document.addEventListener("click", (ev) => { if (!$("#pop-voix").hidden && !$("#pop-voix").contains(ev.target)) $("#pop-voix").hidden = true; });
}

async function basculerPopVoix() {
  const pop = $("#pop-voix");
  if (!pop.hidden) { pop.hidden = true; return; }
  const v = await api.voix();
  etat.audio.voix = v;
  pop.innerHTML = `<span class="lab-c">Voix de lecture</span>` + v.voix.map((x) => `
    <div class="v-ligne ${x.id === v.choisie ? "on" : ""}">
      <button class="pb" data-ecouter="${x.id}" aria-label="Écouter ${echap(x.nom)}" title="Écouter un extrait">${ICONES.play}</button>
      <div class="v-txt" data-choisir="${x.id}"><b>${echap(x.nom)}</b><span>${echap(x.description)}</span></div></div>`).join("")
    + `<p class="note-pop">Changer de voix refait l'audio des livres (environ 20 fois plus vite que la durée d'écoute).</p>`;
  pop.hidden = false;
  $$("#pop-voix [data-ecouter]").forEach((bt) => (bt.onclick = async (ev) => {
    ev.stopPropagation();
    bt.disabled = true;
    try { const src = await api.extrait_voix(bt.dataset.ecouter); const ex = new Audio(src); ex.play(); }
    catch (e) { toast("Extrait impossible : vérifie la connexion Internet."); }
    bt.disabled = false;
  }));
  $$("#pop-voix [data-choisir]").forEach((d) => (d.onclick = async (ev) => {
    ev.stopPropagation();
    await api.choisir_voix(d.dataset.choisir);
    $("#voix-nom").textContent = v.voix.find((x) => x.id === d.dataset.choisir).nom;
    pop.hidden = true;
    etat.audio.chargee = null;
    $("#audio").removeAttribute("src");
    majAudio();
  }));
}

// ---------- lecteur (phase 3) : surlignage, défilement, clic, reprise ----------
etat.suivi = { mots: [], blocs: {}, courant: null, mot: -1, manuelJusqua: 0, dernierSauve: 0, durees: null };

function preparerMinutage(m) {
  const mots = [], blocs = {};
  for (const b of m.blocs) {
    blocs[b.bloc] = { debut: b.debut, fin: b.fin };
    for (const w of b.mots) if (w.a >= 0) mots.push({ t: w.d, f: w.f, bloc: b.bloc, a: w.a, b: w.b });
  }
  mots.sort((x, y) => x.t - y.t);
  etat.suivi.mots = mots;
  etat.suivi.blocs = blocs;
  etat.suivi.mot = -1;
}

function motA(t) {
  const m = etat.suivi.mots;
  let lo = 0, hi = m.length - 1, res = -1;
  // + 0,1 s : un mot sur le point de commencer est déjà allumé (après un clic ou un saut).
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (m[mid].t <= t + 0.1) { res = mid; lo = mid + 1; } else hi = mid - 1; }
  return res;
}

// Limites de la phrase qui contient la position p (fin de phrase : . ! ? … ; suivis d'un espace).
function phraseAutour(texte, p) {
  let debut = 0, fin = texte.length;
  const re = /[.!?…;](?:\s*[»"”)])?\s+/g;
  let m;
  while ((m = re.exec(texte))) {
    const f = m.index + m[0].length;
    if (f <= p) debut = f; else { fin = f; break; }
  }
  return [debut, fin];
}

function texteBloc(id) {
  for (const s of etat.livre.sections) for (const b of s.blocs) if (b.id === id) return b.texte;
  return "";
}

function majSurlignage(force = false) {
  const a = $("#audio"), s = etat.suivi;
  if (!s.mots.length || $("#vue-lecture").hidden) return;
  const i = motA(a.currentTime);
  if (i === s.mot && !force) return;
  s.mot = i;
  const t = a.currentTime;
  const m = i >= 0 && t <= s.mots[i].f + 1.2 ? s.mots[i] : null;  // dans un silence long : rien de surligné
  const blocCourant = m ? m.bloc : null;
  // Blocs déjà lus en gris ; le bloc courant est redessiné avec sa phrase et son mot.
  $$("#page-lecture .lu-bloc").forEach((el) => {
    const id = el.dataset.id, info = s.blocs[id];
    if (id === blocCourant) return;
    if (el.dataset.deco) { el.textContent = texteBloc(id); delete el.dataset.deco; }
    el.classList.toggle("lue", !!info && info.fin <= t);
  });
  if (!m) { s.courant = null; return; }
  const el = $(`#page-lecture .lu-bloc[data-id="${m.bloc}"]`);
  if (!el) return;
  const txt = texteBloc(m.bloc);
  const [p0, p1] = phraseAutour(txt, m.a);
  el.classList.remove("lue");
  el.dataset.deco = "1";
  el.innerHTML = `<span class="ph lue">${echap(txt.slice(0, p0))}</span><span class="ph cours">${echap(txt.slice(p0, m.a))}<mark>${echap(txt.slice(m.a, m.b))}</mark>${echap(txt.slice(m.b, p1))}</span>${echap(txt.slice(p1))}`;
  s.courant = m.bloc;
  // Défilement : garder le mot vers le milieu, sauf si l'utilisateur fait défiler lui-même.
  const mk = el.querySelector("mark"), zone = $("#zone-lecture");
  if (mk && Date.now() > s.manuelJusqua) {
    const rz = zone.getBoundingClientRect(), rm = mk.getBoundingClientRect();
    if (rm.top < rz.top + rz.height * 0.2 || rm.bottom > rz.top + rz.height * 0.7)
      zone.scrollTo({ top: zone.scrollTop + (rm.top - rz.top) - rz.height * 0.38, behavior: "smooth" });
  }
  if (!a.paused && Date.now() - s.dernierSauve > 5000) sauverPosition();
}

function boucleSuivi() {
  const a = $("#audio");
  majSurlignage();
  if ($("#a-t")) {
    $("#a-t").textContent = fmt(a.currentTime);
  }
  majProgression(false);
  if (!a.paused) requestAnimationFrame(boucleSuivi);
}

function brancherSuivi() {
  const zone = $("#zone-lecture");
  const manuel = () => (etat.suivi.manuelJusqua = Date.now() + 5000);
  zone.addEventListener("wheel", manuel, { passive: true });
  zone.addEventListener("touchmove", manuel, { passive: true });
  zone.addEventListener("mousedown", (e) => { if (e.target === zone) manuel(); });
  // Clic sur une phrase : la lecture part du début de cette phrase.
  $("#page-lecture").addEventListener("click", async (e) => {
    const el = e.target.closest(".lu-bloc");
    if (!el || (window.getSelection() && !window.getSelection().isCollapsed)) return;
    if (!sectionPrete()) { toast("Crée d'abord l'audio pour cliquer sur une phrase."); return; }
    let offset = 0;
    const r = document.caretRangeFromPoint ? document.caretRangeFromPoint(e.clientX, e.clientY) : null;
    if (r && el.contains(r.startContainer)) {
      const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let n;
      while ((n = w.nextNode())) { if (n === r.startContainer) { offset += r.startOffset; break; } offset += n.length; }
    }
    const [p0] = phraseAutour(texteBloc(el.dataset.id), offset);
    if (!(await chargerAudioSection(false))) return;
    const mots = etat.suivi.mots.filter((m) => m.bloc === el.dataset.id);
    const cible = mots.find((m) => m.a >= p0) || mots[0];
    const a = $("#audio");
    a.currentTime = cible ? Math.max(0, cible.t - 0.05) : (etat.suivi.blocs[el.dataset.id] || { debut: 0 }).debut;
    etat.suivi.manuelJusqua = 0;
    try { await a.play(); } catch (err) { /* refusé */ }
  });
}

function sauverPosition() {
  const a = $("#audio"), l = etat.livre, s = etat.section;
  if (!l || !s || !etat.audio.chargee || !etat.audio.chargee.startsWith(l.id + "|" + s.id + "|")) return;
  const positions = { ...(etat.reglages.positions || {}) };
  positions[l.id] = { section: s.id, mode: aDesNotes(l) ? etat.mode : "texte", t: Math.round(a.currentTime * 10) / 10, quand: Date.now() };
  etat.suivi.dernierSauve = Date.now();
  sauverReglages({ positions });
  if (a.duration && a.currentTime / a.duration > 0.97) marquerEcoutee(s.id);
}

function marquerEcoutee(id) {
  const l = etat.livre, tout = { ...(etat.reglages.ecoutees || {}) };
  const liste = new Set(tout[l.id] || []);
  if (liste.has(id)) return;
  liste.add(id);
  tout[l.id] = [...liste];
  sauverReglages({ ecoutees: tout });
  dessinerSections();
}

async function chargerDurees() {
  const l = etat.livre;
  etat.suivi.durees = await api.durees_sections(l.id, aDesNotes(l) ? etat.mode : "texte");
  majProgression();
}

// Barre de la carte du livre : où j'en suis dans le livre, et le temps qui reste.
function majProgression(complet = true) {
  const l = etat.livre, d = etat.suivi.durees, a = $("#audio");
  if (!l || !etat.section) return;
  const i = l.sections.indexOf(etat.section);
  const pl = (n, mot) => `${n.toLocaleString("fr-CA")} ${mot}${n > 1 ? "s" : ""}`;
  // Pas encore d'audio : on montre la taille du livre, pas un pourcentage qui ne veut rien dire.
  if (!d || !d.some((x) => x)) {
    $("#livre-progres").style.width = "0%";
    $("#livre-info").textContent = `${l.pages.length ? pl(l.pages.length, l.meta.type === "images" ? "image" : "page") + " · " : ""}${pl(l.sections.length, "section")} · audio à créer`;
    return;
  }
  let pc, reste = null;
  if (d.every((x) => x)) {
    const total = d.reduce((x, y) => x + y, 0);
    const avant = d.slice(0, i).reduce((x, y) => x + y, 0) + (a.currentTime || 0);
    pc = total ? avant / total : 0;
    reste = (total - avant) / (a.playbackRate || 1);  // temps réel d'écoute à la vitesse choisie
  } else pc = (i + (a.duration ? a.currentTime / a.duration : 0)) / l.sections.length;
  pc = Math.min(pc, 0.999);  // jamais 100 % avant la fin
  $("#livre-progres").style.width = `${pc > 0 ? Math.max(1, pc * 100) : 0}%`;
  if (complet || Date.now() - (etat.suivi.texteProgres || 0) > 2000) {
    etat.suivi.texteProgres = Date.now();
    const pctxt = pc <= 0 ? "0" : pc < 0.001 ? "< 0,1" : pc < 0.1 ? (Math.floor(pc * 1000) / 10).toLocaleString("fr-CA") : Math.floor(pc * 100);
    const audioPartiel = d.every((x) => x) ? "" : " · audio en partie";
    $("#livre-info").textContent = reste !== null ? `${pctxt} % · ${duree(reste)} restantes` : `${pctxt} % · section ${i + 1} sur ${l.sections.length}${audioPartiel}`;
  }
}

function majMediaSession() {
  if (!("mediaSession" in navigator) || !etat.section) return;
  const s = etat.section;
  navigator.mediaSession.metadata = new MediaMetadata({ title: (s.ref ? s.ref + " · " : "") + s.titre, album: etat.livre.titre,
    artist: "Lecteur · " + ($("#voix-nom").textContent || "") });
}
if ("mediaSession" in navigator) {
  const ms = navigator.mediaSession;
  ms.setActionHandler("play", () => basculerLecture());
  ms.setActionHandler("pause", () => $("#audio").pause());
  ms.setActionHandler("seekbackward", () => sauter(-15));
  ms.setActionHandler("seekforward", () => sauter(15));
  ms.setActionHandler("previoustrack", () => changerSection(-1, true));
  ms.setActionHandler("nexttrack", () => changerSection(1, true));
}

// ---------- export clé USB (phase 2.4) ----------
etat.exp = { plan: null, dest: null, mode: "mixte", vitesse: 1, minuterie: null, etape: "pret" };
const VIT_EXPORT = [1, 1.1, 1.25, 1.5, 1.75, 2];
const mo = (o) => (o >= 1e9 ? (o / 1e9).toLocaleString("fr-CA", { maximumFractionDigits: 1 }) + " Go" : Math.max(1, Math.round(o / 1e6)).toLocaleString("fr-CA") + " Mo");
const duree = (s) => { s = Math.round(s || 0); if (s < 60) return `${s} s`; const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`; };
const ICONE_CLE = '<svg viewBox="0 0 24 24"><rect x="7" y="9" width="10" height="13" rx="2"/><path d="M9 9V3h6v6"/></svg>';
const ICONE_DOSSIER = '<svg viewBox="0 0 24 24"><path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>';

async function ouvrirExport() {
  if (!etat.livre) return;
  const r = etat.reglages.export || {};
  etat.exp.mode = aDesNotes(etat.livre) ? (r.mode || etat.mode || "mixte") : "texte";
  etat.exp.vitesse = r.vitesse || 1;
  etat.exp.etape = "pret";
  $("#export").hidden = false;
  $("#exp-sous").textContent = `${etat.livre.titre} · ${etat.livre.sections.length} sections`;
  await chargerPlanExport();
}
function fermerExport() { if (etat.exp.etape !== "copie") { $("#export").hidden = true; clearTimeout(etat.exp.minuterie); } }

async function chargerPlanExport() {
  const p = await api.plan_export(etat.livre.id, etat.exp.mode, etat.exp.vitesse);
  etat.exp.plan = p;
  if (!etat.exp.dest || (etat.exp.dest.lettre && !p.cles.some((c) => c.lettre === etat.exp.dest.lettre)))
    etat.exp.dest = p.cles[0] ? { lettre: p.cles[0].lettre, chemin: p.cles[0].lettre + "\\" } : null;
  dessinerExport();
}

function dessinerExport() {
  const p = etat.exp.plan, d = etat.exp.dest, corps = $("#exp-corps"), boutons = $("#exp-boutons");
  if (etat.exp.etape === "copie" || etat.exp.etape === "fini") return dessinerCopie();
  const cles = p.cles.map((c) => {
    const pris = 1 - c.libre / c.total;
    return `<button class="cle ${d && d.lettre === c.lettre ? "on" : ""}" data-lettre="${c.lettre}">
      <span class="ic">${ICONE_CLE}</span><span class="c-txt"><span class="c-l1"><b>${echap(c.nom)} (${c.lettre})</b>
      <span class="mono petit">${mo(c.libre)} libres sur ${mo(c.total)}</span></span><span class="rail"><i style="width:${Math.max(2, pris * 100)}%"></i></span></span></button>`;
  }).join("");
  const dossierPerso = d && !d.lettre ? `<button class="cle on"><span class="ic">${ICONE_DOSSIER}</span><span class="c-txt"><span class="c-l1"><b>${echap(d.chemin)}</b></span></span></button>` : "";
  const aucune = !p.cles.length && !dossierPerso ? `<div class="avert"><span>Aucune clé USB détectée. Branche-la, puis clique sur « Actualiser ».</span></div>` : "";
  const manque = p.prets < p.total ? `<div class="avert"><span>L'audio n'est pas complet : <b>${p.prets} sections sur ${p.total}</b> sont prêtes. Seules celles-ci seront copiées.</span>
      <button class="pil" id="exp-gen">Créer le reste de l'audio</button></div>` : "";
  const cle = d && d.lettre ? p.cles.find((c) => c.lettre === d.lettre) : null;
  const tropPetit = cle && p.octets > cle.libre ? `<div class="avert"><span>Pas assez de place sur la clé : il faut environ ${mo(p.octets)}.</span></div>` : "";
  const segMode = aDesNotes(etat.livre) ? `<div><span class="lab-c">Quoi copier</span><div class="seg" id="exp-modes" style="width:max-content;margin-top:6px">
      ${[["texte", "Texte"], ["notes", "Notes"], ["mixte", "Texte + notes"]].map(([m, n]) => `<button data-m="${m}" class="${m === etat.exp.mode ? "on" : ""}">${n}</button>`).join("")}</div></div>` : "";
  const fich = p.fichiers.slice(0, 8).map((f) => `<div class="f ${f.duree ? "" : "manque"}"><span class="nom">${echap(f.fichier)}</span><span class="d">${f.duree ? fmt(f.duree) : "pas d'audio"}</span></div>`).join("")
    + (p.fichiers.length > 8 ? `<div class="f"><span class="nom petit">… et ${p.fichiers.length - 8} autres</span></div>` : "");
  corps.innerHTML = `
    <div><span class="lab-c">Où copier</span><div class="cles" style="margin-top:6px">${cles}${dossierPerso}${aucune}</div>
      <div class="liens-cle" style="margin-top:6px"><button class="lien" id="exp-actu">Actualiser</button><button class="lien" id="exp-dossier">Choisir un dossier…</button></div></div>
    ${segMode}
    <div><span class="lab-c">Vitesse dans les MP3</span><div class="seg" id="exp-vit" style="width:max-content;margin-top:6px">
      ${[...new Set([...VIT_EXPORT, etat.reglages.vitesse || 1, etat.exp.vitesse])].sort((x, y) => x - y).map((v) => `<button data-v="${v}" class="${v === etat.exp.vitesse ? "on" : ""}" ${v === (etat.reglages.vitesse || 1) ? 'title="Ta vitesse d\'écoute actuelle"' : ""}>${vitTexte(v)}</button>`).join("")}</div>
      <p class="petit" style="margin:4px 0 0">La radio de l'auto ne peut pas accélérer : la vitesse est intégrée aux fichiers, sans changer la voix.</p></div>
    ${manque}${tropPetit}
    <div class="liste-f" aria-label="Fichiers qui seront copiés">${fich}</div>
    <p class="petit" style="margin:0">${d ? `Dossier <span class="mono">${echap(d.chemin.replace(/\\$/, "") + "\\" + p.dossier)}</span>` : "<b>Choisis une clé USB ou un dossier.</b>"} · titre, livre et n° de piste dans chaque MP3 · copiés un par un dans l'ordre (radios d'auto).</p>`;
  $("#exp-resume").textContent = p.prets ? `${duree(p.duree)} · ${mo(p.octets)}` : "";
  const possible = d && p.prets > 0 && !tropPetit;
  boutons.innerHTML = `<button class="sec2" id="exp-annuler">Annuler</button><button class="prim" id="exp-go" ${possible ? "" : "disabled"}>Copier ${p.prets} MP3</button>`;
  $$("#exp-corps .cle[data-lettre]").forEach((b) => (b.onclick = () => { etat.exp.dest = { lettre: b.dataset.lettre, chemin: b.dataset.lettre + "\\" }; dessinerExport(); }));
  $("#exp-actu").onclick = chargerPlanExport;
  $("#exp-dossier").onclick = async () => { const c = await api.choisir_dossier(); if (c) { etat.exp.dest = { lettre: null, chemin: c }; dessinerExport(); } };
  $$("#exp-modes button").forEach((b) => (b.onclick = () => { etat.exp.mode = b.dataset.m; chargerPlanExport(); }));
  $$("#exp-vit button").forEach((b) => (b.onclick = () => { etat.exp.vitesse = Number(b.dataset.v); chargerPlanExport(); }));
  if ($("#exp-gen")) $("#exp-gen").onclick = async () => { await api.generer_audio(etat.livre.id); fermerExport(); majAudio(); toast("Création de l'audio lancée."); };
  $("#exp-annuler").onclick = fermerExport;
  $("#exp-go").onclick = lancerExport;
}

async function lancerExport() {
  const d = etat.exp.dest;
  await api.exporter_usb(etat.livre.id, d.chemin, etat.exp.mode, etat.exp.vitesse);
  etat.reglages.export = { mode: etat.exp.mode, vitesse: etat.exp.vitesse };
  etat.exp.etape = "copie";
  suivreExport();
}

async function suivreExport() {
  const x = await api.etat_export();
  etat.exp.x = x;
  if (!x.en_cours) etat.exp.etape = "fini";
  dessinerCopie();
  if (x.en_cours) etat.exp.minuterie = setTimeout(suivreExport, 700);
}

function dessinerCopie() {
  const x = etat.exp.x || {}, corps = $("#exp-corps"), boutons = $("#exp-boutons"), d = etat.exp.dest;
  if (etat.exp.etape === "copie") {
    const pc = x.total ? Math.max(1, Math.floor((x.fait / x.total) * 100)) : 1;
    corps.innerHTML = `<div style="display:flex;flex-direction:column;gap:8px">
      <div class="ligne-progres"><span>${x.fichier ? "Copie de <span class=\"mono\">" + echap(x.fichier) + "</span>" : "Préparation des fichiers…"}</span><span class="mono">${x.fait || 0} / ${x.total || "…"}</span></div>
      <div class="rail rail-l"><i style="width:${pc}%"></i></div>
      <span class="petit">Ne retire pas la clé pendant la copie.</span></div>`;
    $("#exp-resume").textContent = "";
    boutons.innerHTML = `<button class="sec2" id="exp-stop">Arrêter</button>`;
    $("#exp-stop").onclick = () => api.arreter_export();
    return;
  }
  const r = x.resultat;
  if (x.erreur || !r) {
    corps.innerHTML = `<p class="erreur">${echap(x.erreur || "La copie n'a pas pu se faire.")}</p>`;
    boutons.innerHTML = `<button class="sec2" id="exp-ok">Fermer</button>`;
    $("#exp-ok").onclick = () => { etat.exp.etape = "pret"; fermerExport(); };
    return;
  }
  corps.innerHTML = `<div class="verdict"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M7.5 12.5l3 3 6-7"/></svg>
    <div><b>${r.copies} MP3 copiés et vérifiés${r.interrompu ? " (copie arrêtée)" : ""}</b><span>${duree(r.duree)} d'écoute · ${mo(r.octets)} · <span class="mono">${echap(r.dossier)}</span></span></div></div>`;
  $("#exp-resume").textContent = d && d.lettre ? "Tu peux retirer la clé après l'éjection." : "";
  boutons.innerHTML = `<button class="sec2" id="exp-ouvrir">Ouvrir le dossier</button>${d && d.lettre ? '<button class="prim" id="exp-ejecter">Éjecter la clé</button>' : '<button class="prim" id="exp-ok">Terminé</button>'}`;
  $("#exp-ouvrir").onclick = () => api.ouvrir_dossier(r.dossier);
  if ($("#exp-ok")) $("#exp-ok").onclick = () => { etat.exp.etape = "pret"; fermerExport(); };
  if ($("#exp-ejecter")) $("#exp-ejecter").onclick = async () => {
    const ok = await api.ejecter_cle(d.lettre);
    toast(ok ? "Clé éjectée : tu peux la retirer." : "Windows refuse d'éjecter la clé : ferme les fenêtres qui l'utilisent et réessaie.");
    if (ok) { etat.exp.etape = "pret"; fermerExport(); }
  };
}

// ---------- réglages (phase 4) ----------
const RACCOURCIS = [["Espace", "Lecture / pause"], ["← / →", "Reculer / avancer de 15 s"], ["Ctrl + ← / →", "Section précédente / suivante"],
  ["[ / ]", "Moins vite / plus vite (par 0,05x)"], ["Clic sur une phrase", "Lire à partir de cette phrase"], ["Ctrl + O", "Importer un livre"],
  ["Ctrl + V", "Coller une capture, une adresse web ou un texte"], ["Ctrl + J", "Mode jour / nuit"], ["PgPréc / PgSuiv", "Page précédente / suivante (aperçu)"],
  ["Ctrl + ,", "Réglages"], ["Échap", "Fermer"]];

async function ouvrirReglages() {
  const r = await api.infos_reglages();
  $("#reg-version").textContent = `Lecteur · version ${r.version}`;
  const l = etat.livre;
  const menage = r.menage.fichiers
    ? `${r.menage.fichiers.toLocaleString("fr-CA")} fichiers audio périmés · ${mo(r.menage.octets)}`
    : "Aucun fichier audio périmé.";
  $("#reg-corps").innerHTML = `
    <div class="reg"><div class="reg-l1"><b>Mes données</b><button class="pil" id="reg-donnees">Ouvrir le dossier</button></div>
      <span class="petit mono">${echap(r.donnees)}</span>
      <span class="petit">Livres, audio, corrections apprises et réglages. Ils restent là si tu réinstalles l'app.</span></div>
    <div class="reg"><div class="reg-l1"><b>Ménage de l'audio</b><button class="pil" id="reg-menage" ${r.menage.fichiers ? "" : "disabled"}>Mettre à la corbeille</button></div>
      <span class="petit">${menage} (anciennes versions après une correction ou un changement de voix).</span></div>
    <div class="reg"><b>Corrections retenues · ${Object.keys(r.apprises).length}</b>
      <span class="petit">Faites toutes seules dans tes prochains livres. ✕ = oublier.</span>
      <div class="memo-l">${Object.entries(r.apprises).map(([a, b]) => `<span class="memo"><span class="av">${echap(a)}</span> › <b>${echap(b)}</b><button data-oublier-c="${echap(a)}" title="Oublier cette correction">✕</button></span>`).join("") || '<span class="petit">Aucune.</span>'}</div></div>
    <div class="reg"><b>Mots gardés tels quels · ${r.ignores.length}</b>
      <span class="petit">Jamais signalés « à vérifier ». ✕ = les signaler de nouveau.</span>
      <div class="memo-l">${r.ignores.map((m) => `<span class="memo">${echap(m)}<button data-oublier-m="${echap(m)}" title="Le signaler de nouveau">✕</button></span>`).join("") || '<span class="petit">Aucun.</span>'}</div></div>
    ${l ? `<div class="reg"><div class="reg-l1"><b>Livre ouvert : ${echap(l.titre)}</b><button class="pil" id="reg-suppr">Mettre ce livre à la corbeille</button></div>
      <span class="petit">Le livre, son audio et ses corrections vont dans la corbeille Windows (récupérables). Ton PDF d'origine n'est jamais touché.</span></div>` : ""}
    <div class="reg"><b>Raccourcis clavier</b><div class="raccourcis" style="margin-top:6px">${RACCOURCIS.map(([k, v]) => `<kbd>${k}</kbd><span>${v}</span>`).join("")}</div></div>`;
  $("#reglages").hidden = false;
  $("#reg-donnees").onclick = () => api.ouvrir_donnees();
  const apresOubli = async () => { await ouvrirReglages(); if (etat.livre && !$("#vue-apercu").hidden) chargerDouteux(); };
  $$("#reg-corps [data-oublier-c]").forEach((b) => (b.onclick = async () => { await api.oublier(b.dataset.oublierC, ""); toast(`Correction « ${b.dataset.oublierC} » oubliée.`); apresOubli(); }));
  $$("#reg-corps [data-oublier-m]").forEach((b) => (b.onclick = async () => { await api.oublier("", b.dataset.oublierM); toast(`« ${b.dataset.oublierM} » sera de nouveau signalé.`); apresOubli(); }));
  $("#reg-menage").onclick = async () => {
    const x = await api.faire_menage();
    toast(`${x.fichiers} fichiers mis à la corbeille (${mo(x.octets)} libérés).`);
    ouvrirReglages();
  };
  if ($("#reg-suppr")) $("#reg-suppr").onclick = async (ev) => {
    const b = ev.currentTarget;
    if (!b.dataset.confirme) { b.dataset.confirme = "1"; b.textContent = "Confirmer : à la corbeille"; b.classList.add("ok"); return; }
    $("#audio").pause();
    await api.supprimer(l.id);
    etat.livre = null;
    $("#reglages").hidden = true;
    $("#carte-livre").hidden = true; $("#sections").innerHTML = ""; $("#lab-sections").hidden = true;
    $("#b-apercu").disabled = true; $("#b-usb").disabled = true;
    afficherVue("accueil");
    await chargerLivres();
    toast("Livre mis à la corbeille Windows (récupérable).");
  };
}

// ---------- démarrage ----------
function brancher() {
  $("#b-importer").onclick = () => ouvrirImport();
  $$("#sources-accueil .source").forEach((b) => (b.onclick = () => ouvrirImport(b.dataset.type)));
  $("#b-reglages").onclick = ouvrirReglages;
  $("#reg-fermer").onclick = () => ($("#reglages").hidden = true);
  $("#loupe").onclick = () => ($("#loupe").hidden = true);
  $("#scan").addEventListener("click", async (e) => {
    if (e.target.tagName !== "IMG") return;
    $("#loupe-img").src = e.target.src;  // tout de suite, puis en haute définition
    $("#loupe").hidden = false;
    if (sansPages()) return;
    const r = await api.page(etat.livre.id, etat.ap.page, 1800);
    if (r.image && !$("#loupe").hidden) $("#loupe-img").src = r.image;
  });
  $("#b-etape-voix").onclick = async () => {
    afficherLecture();
    await majAudio();
    if (etat.audio.e && etat.audio.e.fait < etat.audio.e.total && !etat.audio.e.en_cours) {
      await api.generer_audio(etat.livre.id); etat.audio.debut = null; majAudio();
      toast("Création de l'audio lancée.");
    }
  };
  $("#b-theme").onclick = basculerTheme;
  $("#b-apercu").onclick = () => etat.livre && ouvrirApercu();
  $("#b-retour").onclick = () => afficherLecture();
  $("#imp-fermer").onclick = fermerImport;
  $("#imp-annuler").onclick = fermerImport;
  $("#imp-fichier").onclick = choisirFichier;
  $("#imp-images").onclick = choisirImages;
  $$("#imp-onglets button").forEach((b) => (b.onclick = () => choisirOnglet(b.dataset.type)));
  $("#imp-texte").addEventListener("input", majImport);
  $("#imp-url").addEventListener("input", majImport);
  $("#imp-url").addEventListener("keydown", (e) => { if (e.key === "Enter") lancerImport(); });
  document.addEventListener("paste", lireCollage);
  brancherAudio();
  $("#b-usb").onclick = ouvrirExport;
  $("#exp-fermer").onclick = fermerExport;
  $("#imp-go").onclick = lancerImport;
  $("#p-prec").onclick = () => { const p = pagesApercu(); allerPage(p[Math.max(0, p.indexOf(etat.ap.page) - 1)]); };
  $("#p-suiv").onclick = () => { const p = pagesApercu(); allerPage(p[Math.min(p.length - 1, p.indexOf(etat.ap.page) + 1)]); };
  $("#b-lu").onclick = () => {
    etat.ap.lu = !etat.ap.lu;
    $("#b-lu").setAttribute("aria-pressed", String(etat.ap.lu));
    dessinerTexte();
  };
  $$("#pistes button").forEach((b) => (b.onclick = () => choisirPiste(b.dataset.piste)));
  $$("#modes button").forEach((b) => (b.onclick = () => {
    const jouait = !$("#audio").paused;
    etat.mode = b.dataset.mode; sauverReglages({ mode: etat.mode });
    afficherLecture(); chargerDurees();
    if (jouait && sectionPrete()) chargerAudioSection(true);
  }));

  document.addEventListener("keydown", (e) => {
    const edition = e.target.isContentEditable || e.target.tagName === "INPUT";
    if (e.ctrlKey && e.key.toLowerCase() === "o") { e.preventDefault(); ouvrirImport(); }
    else if (e.ctrlKey && e.key.toLowerCase() === "j") { e.preventDefault(); basculerTheme(); }
    else if (e.ctrlKey && e.key === ",") { e.preventDefault(); ouvrirReglages(); }
    else if (e.key === "Escape") {
      if (!$("#loupe").hidden) $("#loupe").hidden = true;
      else if (!$("#reglages").hidden) $("#reglages").hidden = true;
      else if (!$("#export").hidden) fermerExport();
      else if (!$("#import").hidden) fermerImport();
      else if (!$("#vue-apercu").hidden && !edition) afficherLecture();
    } else if (!edition && !$("#vue-apercu").hidden && (e.key === "PageDown" || e.key === "PageUp")) {
      e.preventDefault();
      (e.key === "PageDown" ? $("#p-suiv") : $("#p-prec")).click();
    } else if (!edition && !$("#vue-lecture").hidden && $("#import").hidden && $("#export").hidden && $("#a-play")) {
      // Raccourcis du lecteur audio
      const a = $("#audio");
      if (e.key === " ") { e.preventDefault(); basculerLecture(); }
      else if (e.key === "ArrowLeft" && e.ctrlKey) { e.preventDefault(); changerSection(-1, !a.paused); }
      else if (e.key === "ArrowRight" && e.ctrlKey) { e.preventDefault(); changerSection(1, !a.paused); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); sauter(-15); }
      else if (e.key === "ArrowRight") { e.preventDefault(); sauter(15); }
      else if (e.key === "[" || e.key === "]") {
        const x = regleVitesse((etat.reglages.vitesse || 1) + (e.key === "]" ? VIT_PAS : -VIT_PAS));
        toast(`Vitesse ${vitTexte(x)}`);
      }
    }
  });
}

async function demarrer() {
  api = window.pywebview.api;
  etat.infos = await api.infos();
  etat.reglages = (await api.reglages()) || {};
  appliquerTheme(etat.reglages.theme || "jour");
  etat.mode = etat.reglages.mode || "mixte";
  brancher();
  api.voix().then((v) => { const x = v.voix.find((y) => y.id === v.choisie); if (x) $("#voix-nom").textContent = x.nom; });
  await chargerLivres();
  const dernier = etat.reglages.dernier_livre;
  if (dernier && etat.livres.some((l) => l.id === dernier)) await ouvrirLivre(dernier);
  else afficherVue("accueil");
}

if (window.pywebview && window.pywebview.api) demarrer();
else window.addEventListener("pywebviewready", demarrer);

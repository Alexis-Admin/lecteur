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
  $("#modes").hidden = !aDesNotes(l);
  const memo = (etat.reglages.sections || {})[id];
  etat.section = l.sections.find((s) => s.id === memo) || l.sections[0] || null;
  dessinerSections();
  chargerLivres();
  if (vue === "apercu") ouvrirApercu(); else afficherLecture();
  await majAudio();
  if (vue !== "apercu" && sectionPrete()) chargerAudioSection(false);
}

function dessinerSections() {
  const l = etat.livre;
  $("#lab-sections").hidden = !l.sections.length;
  $("#sections").innerHTML = l.sections.map((s, i) => `
    <button class="sec ${etat.section && s.id === etat.section.id ? "actif" : ""}" data-id="${s.id}" title="${echap((s.ref ? s.ref + " · " : "") + s.titre)}">
      <span class="n mono">${String(i + 1).padStart(2, "0")}</span>
      <span class="t">${echap(s.ref ? s.ref + " · " + s.titre : s.titre)}</span></button>`).join("");
  $$("#sections .sec").forEach((b) => (b.onclick = () => choisirSection(b.dataset.id)));
}

function choisirSection(id) {
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
  let html = "";
  const parties = s.blocs.filter((b) => b.genre === "partie");
  parties.forEach((p) => (html += `<p class="partie">${echap(p.texte)}</p>`));
  html += `<h2>${echap(s.titre)}</h2><p class="ref">${echap(s.ref || "")}${s.ref ? " · " : ""}section ${idx + 1} sur ${l.sections.length}</p>`;
  for (const b of listeDeLecture(s, mode)) {
    if (b.genre === "titre" || b.genre === "partie") continue;
    if (b.piste === "notes") {
      const tag = b.genre === "encadre" ? "Encadré" : (b.ref || "Note");
      html += `<div class="note"><span class="tag">${echap(tag)}</span><span>${echap(b.texte)}</span></div>`;
    } else if (b.genre === "verset") {
      html += `<p><span class="v">${b.v}</span>${echap(b.texte)}</p>`;
    } else {
      html += `<p>${echap(b.texte)}</p>`;
    }
  }
  $("#page-lecture").innerHTML = html;
  $("#zone-lecture").scrollTop = 0;
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
  await chargerDouteux();
  allerPage(etat.ap.page);
}

async function chargerDouteux() {
  $("#liste-douteux").innerHTML = `<div class="chargement">Recherche des mots douteux…</div>`;
  etat.ap.douteux = await api.douteux(etat.livre.id);
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
    return `<div class="bloc ${b.genre}" data-id="${b.id}">${tag}${num}<span class="corps" contenteditable="true" spellcheck="false">${decorer(b.texte, n)}</span></div>`;
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

function dessinerDouteux() {
  const liste = etat.ap.douteux;
  $("#nb-douteux").textContent = liste.length;
  const zone = $("#liste-douteux");
  if (!liste.length) {
    zone.innerHTML = `<div class="tout-bon"><svg viewBox="0 0 24 24"><path d="M5 12l5 5 9-10"/></svg>Rien à vérifier dans ce livre.</div>`;
    return;
  }
  zone.innerHTML = liste.slice(0, 80).map((d, i) => {
    const ex = d.exemples[0] || {};
    const sug = d.suggestions.map((s, k) => `<button class="pil ${k === 0 ? "ok" : ""}" data-i="${i}" data-rempl="${echap(s)}">${echap(s)}</button>`).join("");
    return `<div class="item" data-i="${i}">
      <span class="ctx" data-page="${ex.page || ""}" data-section="${ex.section || ""}" data-piste="${ex.piste || ""}" title="Aller à cet endroit">${echap(ex.avant)}<b>${echap(d.mot)}</b>${echap(ex.apres)}</span>
      <span class="meta">${d.nb} fois${ex.page ? " · p. " + ex.page : ""} · ${echap(d.raison)}</span>
      <div class="acts">${sug}<button class="pil" data-corriger="${i}">Corriger…</button><button class="pil" data-garder="${i}" title="Le mot est bon : ne plus le signaler">Garder</button></div>
    </div>`;
  }).join("") + (liste.length > 80 ? `<p class="petit">… et ${liste.length - 80} autres. Corrige ceux-ci d'abord.</p>` : "");

  $$("#liste-douteux .ctx").forEach((el) => (el.onclick = () => {
    if (el.dataset.piste && aDesNotes(etat.livre)) choisirPiste(el.dataset.piste, false);
    if (sansPages()) allerPage(etat.livre.sections.findIndex((s) => s.id === el.dataset.section) + 1 || 1);
    else if (el.dataset.page) allerPage(Number(el.dataset.page));
  }));
  $$("#liste-douteux [data-rempl]").forEach((el) => (el.onclick = () => remplacer(liste[el.dataset.i].mot, el.dataset.rempl)));
  $$("#liste-douteux [data-garder]").forEach((el) => (el.onclick = async () => {
    await api.ignorer(liste[el.dataset.garder].mot);
    etat.ap.douteux.splice(Number(el.dataset.garder), 1);
    dessinerDouteux(); dessinerTexte();
    toast("Mot gardé : il ne sera plus signalé.");
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

async function remplacer(avant, apres) {
  const retenir = $("#retenir").checked;
  const n = await api.remplacer(etat.livre.id, avant, apres, retenir);
  etat.livre = await api.livre(etat.livre.id);
  etat.section = etat.livre.sections.find((s) => etat.section && s.id === etat.section.id) || etat.livre.sections[0];
  etat.ap.douteux = etat.ap.douteux.filter((d) => d.mot !== avant);
  dessinerDouteux(); dessinerTexte(); dessinerSections();
  toast(`« ${avant} » → « ${apres} » : ${n} remplacement${n > 1 ? "s" : ""}${retenir ? " · retenu pour les prochains livres" : ""}.`);
}

function dessinerAuto() {
  const vus = new Map();
  for (const c of etat.livre.corrections) {
    if (c.apres === "∅" && c.avant.length <= 1) continue;
    const cle = c.avant + "→" + c.apres;
    vus.set(cle, { ...c, nb: (vus.get(cle)?.nb || 0) + 1 });
  }
  const liste = [...vus.values()];
  $("#lab-auto").textContent = `Corrigé automatiquement · ${etat.livre.corrections.length}`;
  const montres = etat.ap.autoTout ? liste : liste.slice(0, 10);
  $("#liste-auto").innerHTML = montres.map((c) => `<span class="av" title="${echap(c.avant)} (p. ${c.page})">${echap(c.avant)}</span><span class="fl">›</span><span class="ap" title="${c.nb} fois">${echap(c.apres === "∅" ? "(retiré)" : c.apres)}</span>`).join("");
  $("#b-plus-auto").hidden = liste.length <= 10 || etat.ap.autoTout;
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
    <button class="prim" id="b-gen" ${e.autre_en_cours || fini ? "disabled" : ""}>${e.fait ? "Continuer" : "Générer l'audio"}</button>`;
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
    <select class="vit" id="a-vit" aria-label="Vitesse de lecture" title="Vitesse : 0,75x à 3x ([ et ])">
      ${VITESSES.map((x) => `<option value="${x}" ${x === v ? "selected" : ""}>${String(x).replace(".", ",")}x</option>`).join("")}</select>`;
  $("#a-play").onclick = basculerLecture;
  $("#a-moins").onclick = () => sauter(-15);
  $("#a-plus").onclick = () => sauter(15);
  $("#a-prec").onclick = () => changerSection(-1, !a.paused);
  $("#a-suiv").onclick = () => changerSection(1, !a.paused);
  $("#a-vit").onchange = (ev) => { const x = Number(ev.target.value); a.playbackRate = x; sauverReglages({ vitesse: x }); };
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
    a.src = r.url;
    a.playbackRate = etat.reglages.vitesse || 1;
  }
  if (jouer) { try { await a.play(); } catch (e) { /* lecture refusée */ } }
  dessinerLecteur();
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
  a.addEventListener("play", () => $("#a-play") && ($("#a-play").innerHTML = ICONES.pause));
  a.addEventListener("pause", () => $("#a-play") && ($("#a-play").innerHTML = ICONES.play));
  a.addEventListener("ended", () => changerSection(1, true));
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

// ---------- démarrage ----------
function brancher() {
  $("#b-importer").onclick = () => ouvrirImport();
  $("#b-importer2").onclick = () => ouvrirImport();
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
  $("#imp-go").onclick = lancerImport;
  $("#p-prec").onclick = () => { const p = pagesApercu(); allerPage(p[Math.max(0, p.indexOf(etat.ap.page) - 1)]); };
  $("#p-suiv").onclick = () => { const p = pagesApercu(); allerPage(p[Math.min(p.length - 1, p.indexOf(etat.ap.page) + 1)]); };
  $("#b-plus-auto").onclick = () => { etat.ap.autoTout = true; dessinerAuto(); };
  $("#b-lu").onclick = () => {
    etat.ap.lu = !etat.ap.lu;
    $("#b-lu").setAttribute("aria-pressed", String(etat.ap.lu));
    dessinerTexte();
  };
  $$("#pistes button").forEach((b) => (b.onclick = () => choisirPiste(b.dataset.piste)));
  $$("#modes button").forEach((b) => (b.onclick = () => { etat.mode = b.dataset.mode; sauverReglages({ mode: etat.mode }); afficherLecture(); }));

  document.addEventListener("keydown", (e) => {
    const edition = e.target.isContentEditable || e.target.tagName === "INPUT";
    if (e.ctrlKey && e.key.toLowerCase() === "o") { e.preventDefault(); ouvrirImport(); }
    else if (e.ctrlKey && e.key.toLowerCase() === "j") { e.preventDefault(); basculerTheme(); }
    else if (e.key === "Escape") {
      if (!$("#import").hidden) fermerImport();
      else if (!$("#vue-apercu").hidden && !edition) afficherLecture();
    } else if (!edition && !$("#vue-apercu").hidden && (e.key === "PageDown" || e.key === "PageUp")) {
      e.preventDefault();
      (e.key === "PageDown" ? $("#p-suiv") : $("#p-prec")).click();
    } else if (!edition && !$("#vue-lecture").hidden && $("#import").hidden && $("#a-play")) {
      // Raccourcis du lecteur audio
      const a = $("#audio");
      if (e.key === " ") { e.preventDefault(); basculerLecture(); }
      else if (e.key === "ArrowLeft" && e.ctrlKey) { e.preventDefault(); changerSection(-1, !a.paused); }
      else if (e.key === "ArrowRight" && e.ctrlKey) { e.preventDefault(); changerSection(1, !a.paused); }
      else if (e.key === "ArrowLeft") { e.preventDefault(); sauter(-15); }
      else if (e.key === "ArrowRight") { e.preventDefault(); sauter(15); }
      else if (e.key === "[" || e.key === "]") {
        const i = VITESSES.indexOf(a.playbackRate);
        const x = VITESSES[Math.min(VITESSES.length - 1, Math.max(0, (i < 0 ? 1 : i) + (e.key === "]" ? 1 : -1)))];
        a.playbackRate = x; sauverReglages({ vitesse: x }); dessinerLecteur(); toast(`Vitesse ${String(x).replace(".", ",")}x`);
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

/* Lecteur — interface (phase 1 : bibliothèque, import, lecture du texte, aperçu et corrections) */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const echap = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let api = null;
const etat = {
  infos: null, reglages: {}, livres: [], livre: null, section: null, mode: "mixte",
  ap: { page: null, piste: "texte", lu: false, douteux: [], autoTout: false, ouverts: new Set() },
  imp: { fichier: null, profil: "bible_etude", enCours: false },
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
      <span class="t">${echap(l.titre)}</span><span class="d mono">${l.pages} p.</span></button>`).join("");
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
  const l = etat.livre;
  $("#carte-livre").hidden = false;
  $("#livre-titre").textContent = l.titre;
  const nomProfil = (etat.infos.profils.find((p) => p.id === l.profil) || {}).nom || "";
  $("#livre-sous").textContent = `${nomProfil}${aDesNotes(l) ? " · texte + notes" : ""}`;
  $("#livre-info").textContent = `${l.pages.length} pages · ${l.sections.length} sections`;
  $("#livre-progres").style.width = "0%";
  $("#b-apercu").disabled = false;
  $("#modes").hidden = !aDesNotes(l);
  const memo = (etat.reglages.sections || {})[id];
  etat.section = l.sections.find((s) => s.id === memo) || l.sections[0] || null;
  dessinerSections();
  chargerLivres();
  if (vue === "apercu") ouvrirApercu(); else afficherLecture();
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
}

// ---------- aperçu ----------
async function ouvrirApercu() {
  afficherVue("apercu");
  const l = etat.livre;
  $("#ap-titre").textContent = l.titre;
  const memo = (etat.reglages.pages_apercu || {})[l.id];
  etat.ap.page = l.pages.includes(memo) ? memo : (etat.section && (etat.section.blocs.find((b) => b.page) || {}).page) || l.pages[0];
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

async function allerPage(n) {
  const l = etat.livre;
  etat.ap.page = n;
  const i = l.pages.indexOf(n);
  $("#p-num").textContent = `p. ${n} · ${i + 1}/${l.pages.length}`;
  $("#p-prec").disabled = i <= 0;
  $("#p-suiv").disabled = i >= l.pages.length - 1;
  const memo = { ...(etat.reglages.pages_apercu || {}) };
  memo[l.id] = n;
  sauverReglages({ pages_apercu: memo });
  dessinerTexte();
  $("#scan").innerHTML = `<div class="chargement">Chargement de la page…</div>`;
  const r = await api.page(l.id, n, 900);
  if (etat.ap.page !== n) return;
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
  const liste = l.sections.flatMap((s) => s.blocs.filter((b) => b.page === n && b.piste === piste));
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
      <span class="ctx" data-page="${ex.page || ""}" data-piste="${ex.piste || ""}" title="Aller à la page ${ex.page || ""}">${echap(ex.avant)}<b>${echap(d.mot)}</b>${echap(ex.apres)}</span>
      <span class="meta">${d.nb} fois · p. ${ex.page || "?"} · ${echap(d.raison)}</span>
      <div class="acts">${sug}<button class="pil" data-corriger="${i}">Corriger…</button><button class="pil" data-garder="${i}" title="Le mot est bon : ne plus le signaler">Garder</button></div>
    </div>`;
  }).join("") + (liste.length > 80 ? `<p class="petit">… et ${liste.length - 80} autres. Corrige ceux-ci d'abord.</p>` : "");

  $$("#liste-douteux .ctx").forEach((el) => (el.onclick = () => {
    if (el.dataset.piste && aDesNotes(etat.livre)) choisirPiste(el.dataset.piste, false);
    if (el.dataset.page) allerPage(Number(el.dataset.page));
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

function ouvrirImport() {
  if (etat.imp.enCours) return;
  etat.imp.fichier = null;
  $("#imp-nom").textContent = "Choisir un PDF…";
  $("#imp-details").textContent = "PDF scanné (CZUR) ou PDF normal";
  $("#imp-titre-livre").value = "";
  $("#imp-pages").value = "";
  $("#imp-erreur").hidden = true;
  $("#imp-progres").hidden = true;
  $("#imp-resume").textContent = "";
  $("#imp-go").disabled = true;
  dessinerProfils();
  $("#import").hidden = false;
  $("#imp-fichier").focus();
}
function fermerImport() { if (!etat.imp.enCours) $("#import").hidden = true; }

function dessinerProfils() {
  $("#imp-profils").innerHTML = etat.infos.profils.map((p) => `
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
  $("#imp-go").disabled = false;
  $("#imp-resume").textContent = "Prêt à importer.";
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
  const f = etat.imp.fichier;
  if (!f) return;
  etat.imp.enCours = true;
  $("#imp-go").disabled = true;
  $("#imp-annuler").disabled = true;
  $("#imp-erreur").hidden = true;
  $("#imp-progres").hidden = false;
  $("#imp-barre").style.width = "1%";
  $("#imp-etape").textContent = "Lecture des pages…";
  try {
    const r = await api.importer(f.chemin, etat.imp.profil, $("#imp-pages").value, $("#imp-titre-livre").value.trim());
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

// ---------- démarrage ----------
function brancher() {
  $("#b-importer").onclick = ouvrirImport;
  $("#b-importer2").onclick = ouvrirImport;
  $("#b-theme").onclick = basculerTheme;
  $("#b-apercu").onclick = () => etat.livre && ouvrirApercu();
  $("#b-retour").onclick = () => afficherLecture();
  $("#imp-fermer").onclick = fermerImport;
  $("#imp-annuler").onclick = fermerImport;
  $("#imp-fichier").onclick = choisirFichier;
  $("#imp-go").onclick = lancerImport;
  $("#p-prec").onclick = () => { const p = etat.livre.pages; allerPage(p[Math.max(0, p.indexOf(etat.ap.page) - 1)]); };
  $("#p-suiv").onclick = () => { const p = etat.livre.pages; allerPage(p[Math.min(p.length - 1, p.indexOf(etat.ap.page) + 1)]); };
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
  await chargerLivres();
  const dernier = etat.reglages.dernier_livre;
  if (dernier && etat.livres.some((l) => l.id === dernier)) await ouvrirLivre(dernier);
  else afficherVue("accueil");
}

if (window.pywebview && window.pywebview.api) demarrer();
else window.addEventListener("pywebviewready", demarrer);

/* Interazioni del sito: tema, ricerca, filtri, animazioni. Nessuna libreria. */
(function () {
  "use strict";

  /* --- tema chiaro/scuro --- */
  var root = document.documentElement;
  var btnTema = document.getElementById("tema");
  if (btnTema) {
    btnTema.addEventListener("click", function () {
      var attuale = root.getAttribute("data-theme");
      if (attuale !== "dark" && attuale !== "light") {
        attuale = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
      }
      var nuovo = attuale === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", nuovo);
      try { localStorage.setItem("tema", nuovo); } catch (e) {}
    });
  }

  /* --- barra di avanzamento sugli articoli --- */
  var articolo = document.querySelector(".articolo__corpo");
  var barra = document.getElementById("progress");
  if (articolo && barra) {
    barra.hidden = false;
    var aggiorna = function () {
      var box = articolo.getBoundingClientRect();
      var totale = box.height - innerHeight;
      var fatto = totale > 0 ? Math.min(1, Math.max(0, -box.top / totale)) : 0;
      barra.style.width = (fatto * 100).toFixed(2) + "%";
    };
    addEventListener("scroll", aggiorna, { passive: true });
    addEventListener("resize", aggiorna);
    aggiorna();
  }

  /* --- comparsa progressiva dei blocchi --- */
  var blocchi = document.querySelectorAll("[data-reveal]");
  if ("IntersectionObserver" in window && blocchi.length) {
    var osservatore = new IntersectionObserver(function (voci) {
      voci.forEach(function (voce) {
        if (voce.isIntersecting) {
          voce.target.classList.add("visibile");
          osservatore.unobserve(voce.target);
        }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    blocchi.forEach(function (b) { osservatore.observe(b); });
  } else {
    blocchi.forEach(function (b) { b.classList.add("visibile"); });
  }

  /* --- filtro per tema in homepage --- */
  var chip = document.querySelectorAll(".chip");
  var righe = document.querySelectorAll(".riga");
  chip.forEach(function (c) {
    c.addEventListener("click", function () {
      var attivo = c.getAttribute("aria-pressed") === "true";
      chip.forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
      c.setAttribute("aria-pressed", attivo ? "false" : "true");
      var tema = attivo ? null : c.dataset.tema;
      righe.forEach(function (r) {
        var temi = (r.dataset.temi || "").split(",");
        r.hidden = !!tema && temi.indexOf(tema) === -1;
      });
    });
  });

  /* --- copia link --- */
  document.querySelectorAll(".copia").forEach(function (b) {
    b.addEventListener("click", function () {
      var testo = b.dataset.url;
      var fine = function () {
        var originale = b.textContent;
        b.textContent = b.dataset.copiato || "Copiato";
        setTimeout(function () { b.textContent = originale; }, 1600);
      };
      if (navigator.clipboard) { navigator.clipboard.writeText(testo).then(fine, fine); }
      else { fine(); }
    });
  });

  /* --- motore di ricerca condiviso --- */
  function normalizza(testo) {
    return (testo || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }
  function cerca(indice, query, tema) {
    var parole = normalizza(query).split(/\s+/).filter(Boolean);
    return (indice || []).filter(function (p) {
      if (tema && (p.g || []).indexOf(tema) === -1) return false;
      if (!parole.length) return !!tema;
      var testo = normalizza(p.t + " " + p.x + " " + (p.g || []).join(" "));
      return parole.every(function (w) { return testo.indexOf(w) !== -1; });
    });
  }
  function evidenzia(testo, query) {
    var parole = normalizza(query).split(/\s+/).filter(Boolean);
    if (!parole.length) return escapeHtml(testo);
    var piatto = normalizza(testo), segmenti = [], usato = new Array(testo.length).fill(false);
    parole.forEach(function (w) {
      var da = 0, i;
      while ((i = piatto.indexOf(w, da)) !== -1) {
        for (var k = i; k < i + w.length && k < usato.length; k++) usato[k] = true;
        da = i + w.length;
      }
    });
    var dentro = false;
    for (var i = 0; i < testo.length; i++) {
      if (usato[i] && !dentro) { segmenti.push("<mark>"); dentro = true; }
      if (!usato[i] && dentro) { segmenti.push("</mark>"); dentro = false; }
      segmenti.push(escapeHtml(testo[i]));
    }
    if (dentro) segmenti.push("</mark>");
    return segmenti.join("");
  }
  function escapeHtml(t) {
    return String(t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }
  function caricaIndice(callback) {
    if (window.__INDICI__) { callback(window.__INDICI__[window.INDICE_RICERCA] || []); return; }
    fetch(window.INDICE_RICERCA || "/ricerca.json")
      .then(function (r) { return r.json(); })
      .then(callback)
      .catch(function () { callback([]); });
  }

  /* --- pagina di ricerca --- */
  var campoPagina = document.getElementById("q-pagina");
  if (campoPagina) {
    var esiti = document.getElementById("esiti");
    var conteggio = document.getElementById("conteggio");
    var pulisci = document.getElementById("pulisci");
    var indicePagina = null;
    var temaAttivo = null;

    var mostra = function () {
      var q = campoPagina.value.trim();
      if (pulisci) pulisci.hidden = !q;
      if (!indicePagina) return;
      if (!q && !temaAttivo) { esiti.innerHTML = ""; conteggio.textContent = ""; return; }
      var trovati = cerca(indicePagina, q, temaAttivo);
      var modello = campoPagina.dataset.conteggio || "{n}";
      conteggio.textContent = trovati.length
        ? modello.replace("{n}", trovati.length)
        : campoPagina.dataset.vuoto;
      esiti.innerHTML = trovati.map(function (p) {
        return '<a class="esito" href="' + p.u + '">' +
          (p.i ? '<span class="esito__img"><img src="/' + p.i + '" alt="" loading="lazy"></span>' : '<span class="esito__img esito__img--vuota"></span>') +
          '<span class="esito__testo"><span class="esito__meta">' + escapeHtml(p.d) +
          ((p.g && p.g.length) ? " · " + escapeHtml(p.g.join(" · ")) : "") + '</span>' +
          '<strong>' + evidenzia(p.t, q) + '</strong>' +
          '<span class="esito__estratto">' + evidenzia(p.x || "", q) + '</span></span></a>';
      }).join("") || '<p class="esito-vuoto">' + escapeHtml(campoPagina.dataset.suggerimento || "") + '</p>';
    };

    caricaIndice(function (d) {
      indicePagina = d;
      var iniziale = new URLSearchParams(location.search).get("q");
      if (iniziale) campoPagina.value = iniziale;
      mostra();
    });
    campoPagina.addEventListener("input", function () {
      mostra();
      var url = new URL(location.href);
      if (campoPagina.value) { url.searchParams.set("q", campoPagina.value); } else { url.searchParams.delete("q"); }
      history.replaceState(null, "", url);
    });
    if (pulisci) pulisci.addEventListener("click", function () { campoPagina.value = ""; mostra(); campoPagina.focus(); });
    document.querySelectorAll(".chip--ricerca").forEach(function (c) {
      c.addEventListener("click", function () {
        var attivo = c.getAttribute("aria-pressed") === "true";
        document.querySelectorAll(".chip--ricerca").forEach(function (x) { x.setAttribute("aria-pressed", "false"); });
        c.setAttribute("aria-pressed", attivo ? "false" : "true");
        temaAttivo = attivo ? null : c.dataset.tema;
        mostra();
      });
    });
  }

  /* --- ingrandimento delle foto negli articoli --- */
  var galleria = document.querySelectorAll(".galleria img[data-grande], .articolo__cover img");
  if (galleria.length) {
    var lente = document.createElement("div");
    lente.className = "lente";
    lente.hidden = true;
    lente.innerHTML = '<img alt=""><button class="lente__chiudi" aria-label="Chiudi">×</button>';
    document.body.appendChild(lente);
    var immagineLente = lente.querySelector("img");
    galleria.forEach(function (img) {
      img.classList.add("ingrandibile");
      img.addEventListener("click", function () {
        immagineLente.src = img.dataset.grande || img.src;
        lente.hidden = false;
        document.body.style.overflow = "hidden";
      });
    });
    var chiudiLente = function () { lente.hidden = true; document.body.style.overflow = ""; };
    lente.addEventListener("click", chiudiLente);
    addEventListener("keydown", function (e) { if (e.key === "Escape") chiudiLente(); });
  }

  /* --- selettore lingua --- */
  var bottoneLingue = document.getElementById('apri-lingue');
  var menuLingue = document.getElementById('menu-lingue');
  if (bottoneLingue && menuLingue) {
    bottoneLingue.addEventListener('click', function (e) {
      e.stopPropagation();
      var aperto = !menuLingue.hidden;
      menuLingue.hidden = aperto;
      bottoneLingue.setAttribute('aria-expanded', String(!aperto));
    });
    document.addEventListener('click', function () {
      menuLingue.hidden = true;
      bottoneLingue.setAttribute('aria-expanded', 'false');
    });
    addEventListener('keydown', function (e) {
      if (e.key === 'Escape') { menuLingue.hidden = true; }
    });
  }

  /* --- ricerca --- */
  var overlay = document.getElementById("ricerca");
  var campo = document.getElementById("q");
  var risultati = document.getElementById("risultati");
  var indice = null;

  function apri() {
    overlay.hidden = false;
    campo.focus();
    if (!indice) { caricaIndice(function (d) { indice = d; }); }
  }
  function chiudi() { overlay.hidden = true; campo.value = ""; risultati.innerHTML = ""; }

  var apriBtn = document.getElementById("apri-ricerca");
  if (apriBtn) apriBtn.addEventListener("click", apri);
  var chiudiBtn = document.getElementById("chiudi-ricerca");
  if (chiudiBtn) chiudiBtn.addEventListener("click", chiudi);
  if (overlay) overlay.addEventListener("click", function (e) { if (e.target === overlay) chiudi(); });

  addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay && !overlay.hidden) chiudi();
    if ((e.key === "/" || (e.key === "k" && (e.metaKey || e.ctrlKey))) && overlay && overlay.hidden) {
      var dentroCampo = /input|textarea/i.test((e.target.tagName || ""));
      if (!dentroCampo) { e.preventDefault(); apri(); }
    }
  });

  if (campo) {
    campo.addEventListener("input", function () {
      var q = campo.value.trim();
      if (!q || !indice) { risultati.innerHTML = ""; return; }
      var tutti = cerca(indice, q, null);
      var trovati = tutti.slice(0, 8);
      var tutti_link = document.getElementById("tutti-risultati");
      if (tutti_link) {
        tutti_link.hidden = tutti.length <= trovati.length;
        tutti_link.href = tutti_link.href.split("?")[0] + "?q=" + encodeURIComponent(q);
      }
      risultati.innerHTML = trovati.length
        ? trovati.map(function (p) {
            return '<a href="' + p.u + '"><strong>' + evidenzia(p.t, q) + "</strong><em>" + escapeHtml(p.d) +
              (p.g && p.g.length ? " · " + p.g.join(" · ") : "") + "</em></a>";
          }).join("")
        : '<a><strong>' + (campo.dataset.vuoto || 'Nessun risultato') + '</strong><em>' +
          (campo.dataset.suggerimento || '') + '</em></a>';
    });
  }
})();

/* Rol 3 · Mejoras de la página del portal cuando corre con los agentes del Rol 3.
 *
 * No modifica portal/web/: el lanzador scripts/rol3/portal_rol3.py añade este script al index.html
 * que entrega. Observa el DOM y, cuando el portal pinta algo, lo ajusta:
 *   1. Tabla de candidatos: desplazamiento interno (el detalle queda a la vista), encabezado fijo,
 *      filtro por columna y fila seleccionada resaltada.
 *   2. «Estado del sistema» (vista Lote): el portal dice que analista y auditor son dobles del Rol 4;
 *      con este lanzador son los del Rol 3, y así lo muestra.
 *   3. Bandeja: detenidos con filtros (por defecto, solo los que esperan revisión), mensajes por
 *      aprobar con desplazamiento y búsqueda, y la agenda de entrevistas resultante.
 *   4. Textos: sin comillas invertidas de markdown ni referencias internas a hallazgos.
 */
(() => {
  "use strict";

  const norm = (s) => (s || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").trim();
  const MAX_OPCIONES = 12;  // con más valores distintos, el filtro es texto libre

  /* ------------------------------------------------------------ 1. tabla */
  const encabezados = (tabla) => [...tabla.querySelectorAll("thead tr:first-child th")].map((th) => norm(th.textContent));
  function esTablaCandidatos(tabla) {
    const ths = encabezados(tabla);
    return ths.includes("cv") && ths.includes("veredicto");
  }
  function esTablaDetenidos(tabla) {
    return encabezados(tabla).includes("veredicto del auditor");
  }
  function esTablaAgenda(tabla) {
    return Boolean(tabla.closest(".rol3-agenda"));
  }
  function esTablaEvidencia(tabla) {
    const ths = encabezados(tabla);
    return ths.includes("hash") && ths.includes("componente");
  }

  /* ------------------------------------------- evidencia: etiquetas legibles
   * Solo PRESENTACIÓN: el registro (y su hash) no se toca. Los nombres de componente los pone el
   * grafo del Rol 1 (cvagent/workflow/graph.py) y no coinciden con los roles del grupo. */
  const QUIEN = [
    [/^rol-2-adapter$/, /^ficha_created$/, "analista · Rol 3"],
    [/^rol-3-adapter$/, /^verdict_created$/, "motor de reglas · Rol 2"],
    [/^rol-3-adapter$/, /^audit_/, "auditor · Rol 3"],
    [/^rol-4-adapter$/, /^message_ready$/, "agendador · Rol 3"],
    [/^human-approval$/, /./, "persona"],
    [/^simulated-delivery$/, /./, "envío simulado · Rol 1"],
    [/^workflow$/, /./, "grafo · Rol 1"],
  ];
  let cvPorCaso = null;           // correlation_id → cv_id (de /api/candidatos)
  async function cargarCvPorCaso() {
    try {
      const lista = await fetch("/api/candidatos").then((r) => r.json());
      cvPorCaso = Object.fromEntries(lista.map((c) => [c.correlation_id, c.cv_id]));
    } catch { cvPorCaso = {}; }
  }
  function anotarEvidencia(tabla) {
    if (!cvPorCaso) return;
    const ths = encabezados(tabla);
    const iCaso = ths.indexOf("caso"), iComp = ths.indexOf("componente"), iRazon = ths.indexOf("razon");
    tabla.querySelectorAll("tbody tr").forEach((tr) => {
      if (tr.dataset.rol3) return;
      tr.dataset.rol3 = "1";
      const code = tr.children[iCaso]?.querySelector("code");
      const cv = code && cvPorCaso[code.title];
      if (cv) tr.children[iCaso].prepend(Object.assign(document.createElement("strong"), { className: "rol3-cv", textContent: cv + " " }));
      const comp = valorCelda(tr.children[iComp]), razon = valorCelda(tr.children[iRazon]);
      const q = QUIEN.find(([c, r]) => c.test(comp) && r.test(razon));
      if (q) tr.children[iComp].append(Object.assign(document.createElement("div"), { className: "rol3-quien", textContent: q[2] }));
    });
    // el selector de casos del portal muestra UUID: se le antepone el CV
    tabla.closest(".carta")?.querySelectorAll(".carta-cabecera select option").forEach((o) => {
      if (o.value && cvPorCaso[o.value] && !o.dataset.rol3) { o.dataset.rol3 = "1"; o.textContent = `${cvPorCaso[o.value]} · ${o.textContent}`; }
    });
  }

  function valorCelda(td) {
    return ((td && (td.innerText ?? td.textContent)) || "").replace(/\s+/g, " ").trim();
  }

  // "≥0.7", ">=70%", "<0,5", "0.8" … sobre columnas numéricas
  function cumpleNumero(texto, filtro) {
    const m = filtro.replace(",", ".").match(/^(>=|<=|>|<|=|≥|≤)?\s*(-?\d+(?:\.\d+)?)\s*(%)?$/);
    if (!m) return null;
    const celdaPct = texto.includes("%");
    let n = parseFloat(valorNumerico(texto));
    if (Number.isNaN(n)) return false;
    if (celdaPct) n /= 100;                         // todo se compara como fracción 0–1
    let objetivo = parseFloat(m[2]);
    if (m[3] || (celdaPct && objetivo > 1)) objetivo /= 100;
    switch (m[1]) {
      case ">": return n > objetivo;
      case "<": return n < objetivo;
      case ">=": case "≥": return n >= objetivo;
      case "<=": case "≤": return n <= objetivo;
      default: return Math.abs(n - objetivo) < 1e-9;
    }
  }
  const valorNumerico = (t) => (t.match(/-?\d+(?:[.,]\d+)?/) || [""])[0].replace(",", ".");

  function mejorarTabla(tabla) {
    if (tabla.dataset.rol3) return;
    tabla.dataset.rol3 = "1";

    const envoltura = tabla.closest(".tabla-envoltura") || tabla.parentElement;
    envoltura.classList.add("rol3-scroll");

    const cabecera = tabla.querySelector("thead tr");
    const columnas = [...cabecera.children].map((th) => th.textContent.trim());
    const filas = () => [...tabla.querySelectorAll("tbody tr:not(.rol3-msg)")];
    const filaFiltros = document.createElement("tr");
    filaFiltros.className = "rol3-filtros";
    const filtros = [];

    columnas.forEach((nombre, i) => {
      const th = document.createElement("th");
      if (!nombre) { filtros.push({ control: { value: "" }, numerica: false }); filaFiltros.append(th); return; }
      const valores = [...new Set(filas().map((tr) => valorCelda(tr.children[i])))].filter(Boolean).sort();
      const numerica = filas().every((tr) => /^[-\d.,%\s—]*$/.test(valorCelda(tr.children[i])));
      let control;
      if (!numerica && valores.length > 1 && valores.length <= MAX_OPCIONES) {
        control = document.createElement("select");
        control.append(new Option("Todos", ""));
        valores.forEach((v) => control.append(new Option(v, v)));
      } else {
        control = document.createElement("input");
        control.type = "search";
        control.placeholder = numerica ? "≥ 0.7" : "Buscar…";
        control.title = numerica ? "Número exacto o comparación: >0.8, <=70%, =3" : "Contiene el texto";
      }
      control.setAttribute("aria-label", `Filtrar por ${nombre}`);
      control.addEventListener("input", aplicar);
      control.addEventListener("click", (e) => e.stopPropagation());
      filtros.push({ control, numerica });
      th.append(control);
      filaFiltros.append(th);
    });
    cabecera.after(filaFiltros);

    // contador junto al título de la carta («Evaluables (28)»)
    const carta = tabla.closest(".carta");
    const titulo = carta?.querySelector(".carta-cabecera h4");
    const contador = document.createElement("span");
    contador.className = "rol3-contador";
    titulo?.append(contador);

    const limpiar = document.createElement("button");
    limpiar.type = "button";
    limpiar.className = "btn rol3-limpiar";
    limpiar.textContent = "Limpiar filtros";
    limpiar.addEventListener("click", () => { filtros.forEach((f) => (f.control.value = "")); aplicar(); });
    carta?.querySelector(".carta-cabecera")?.append(limpiar);

    // si el portal repinta las filas (p. ej. el selector de casos de Evidencia), se vuelve a filtrar
    new MutationObserver(() => { if (esTablaEvidencia(tabla)) anotarEvidencia(tabla); aplicar(); })
      .observe(tabla.querySelector("tbody"), { childList: true });

    function aplicar() {
      let visibles = 0;
      const total = filas().length;
      filas().forEach((tr) => {
        const ok = filtros.every(({ control, numerica }, i) => {
          const f = control.value.trim();
          if (!f) return true;
          const texto = valorCelda(tr.children[i]);
          if (control.tagName === "SELECT") return texto === f;
          if (numerica) { const r = cumpleNumero(texto, f); if (r !== null) return r; }
          return norm(texto).includes(norm(f));
        });
        tr.hidden = !ok;
        if (tr.nextElementSibling?.classList.contains("rol3-msg")) tr.nextElementSibling.hidden = !ok;
        if (ok) visibles++;
      });
      const activos = filtros.some((f) => f.control.value.trim());
      contador.textContent = activos ? ` · mostrando ${visibles} de ${total}` : "";
      limpiar.style.display = activos ? "" : "none";  // .btn fija display: [hidden] no basta
    }
    aplicar();
    tabla.rol3Filtrar = (columna, valor) => {   // para fijar un filtro desde fuera (detenidos)
      const i = columnas.findIndex((c) => norm(c) === norm(columna));
      const c = filtros[i]?.control;
      if (c?.tagName === "SELECT" && [...c.options].some((o) => o.value === valor)) { c.value = valor; aplicar(); }
    };

    // fila seleccionada (solo candidatos: el clic muestra su detalle)
    if (!esTablaCandidatos(tabla)) return;
    tabla.querySelector("tbody").addEventListener("click", (e) => {
      const tr = e.target.closest("tr");
      if (!tr) return;
      filas().forEach((f) => f.classList.toggle("rol3-sel", f === tr));
    });
    filas()[0]?.classList.add("rol3-sel");
  }

  /* ------------------------------------------------- 2. estado del sistema */
  function corregirEstado(raiz) {
    for (const strong of raiz.querySelectorAll("strong")) {
      if (strong.dataset.rol3 || strong.textContent.trim() !== "Analista y auditor") continue;
      strong.dataset.rol3 = "1";
      strong.textContent = "Analista, auditor y agendador";
      const bloque = strong.closest("div")?.parentElement;
      const pastilla = bloque?.querySelector(".pastilla");
      if (pastilla) {
        pastilla.className = "pastilla pastilla-ok";
        pastilla.replaceChildren(Object.assign(document.createElement("span"), { className: "punto" }),
          document.createTextNode("real · Rol 3"));
      }
      const nota = bloque?.querySelector("p");
      if (nota) {
        nota.textContent = "El analista usa el LLM sobre el CV anonimizado (o la versión léxica si no hay " +
          "ficha generada; cada caso indica cuál). El auditor puede bloquear, nunca aprobar. Puntaje con la " +
          "rúbrica provisional.";
      }
    }
  }


  /* ------------------------------------------- 3. agenda de entrevistas (Bandeja) */
  const fmtFecha = new Intl.DateTimeFormat("es-CO", { weekday: "long", day: "numeric", month: "long",
    hour: "2-digit", minute: "2-digit", timeZone: "America/Bogota" });
  const fmtHora = new Intl.DateTimeFormat("es-CO", { hour: "2-digit", minute: "2-digit", timeZone: "America/Bogota" });
  const el = (tag, clase, texto) => Object.assign(document.createElement(tag), clase ? { className: clase } : {},
    texto !== undefined ? { textContent: texto } : {});

  async function pintarAgenda() {
    if (!location.hash.startsWith("#/bandeja")) return;
    const contenido = document.getElementById("contenido");
    const columna = contenido?.firstElementChild;
    if (!columna || columna.querySelector(".rol3-agenda") || columna.dataset.rol3Agenda) return;
    columna.dataset.rol3Agenda = "1";
    let agenda = [];
    try { agenda = await fetch("/api/rol3/agenda").then((r) => r.json()); } catch { return; }
    if (!agenda.length || !columna.isConnected) return;

    const carta = el("div", "carta rol3-agenda");
    const cab = el("div", "carta-cabecera");
    const tit = el("div", "crece");
    tit.append(el("h4", "sin-margen", `Agenda de entrevistas (${agenda.length})`),
      el("p", "diminuto apagado sin-margen", "Propuesta por el agendador con las plantillas aprobadas y el " +
        "calendario del panel. El nombre del candidato se completa al enviar."));
    cab.append(tit);
    const tabla = el("table");
    const thead = el("thead"), trh = el("tr");
    ["CV", "Fecha y hora (Bogotá)", "Plantilla", "Estado", ""].forEach((t) => trh.append(el("th", "", t)));
    thead.append(trh);
    const tbody = el("tbody");
    agenda.forEach((a) => {
      const tr = el("tr");
      const ini = new Date(a.inicio), fin = new Date(a.fin);
      const estado = a.enviado ? ["enviado (simulado)", "ok"]
        : a.estado_caso === "pendiente_aprobacion_mensaje" ? ["mensaje por aprobar", "alerta"]
        : [String(a.estado_caso || "—").replace(/_/g, " "), "neutra"];
      const pild = el("span", `pastilla pastilla-${estado[1]}`, estado[0]);
      const ver = el("button", "btn rol3-limpiar", "Ver mensaje");
      const fila_msg = el("tr", "rol3-msg");
      const td_msg = el("td");
      td_msg.colSpan = 5;
      td_msg.append(el("pre", "rol3-pre", a.texto_exacto));
      fila_msg.append(td_msg);
      fila_msg.style.display = "none";
      ver.addEventListener("click", () => { fila_msg.style.display = fila_msg.style.display ? "" : "none"; });
      const tdEstado = el("td"); tdEstado.append(pild);
      const tdVer = el("td"); tdVer.append(ver);
      tr.append(el("td", "", a.cv_id), el("td", "nowrap", `${fmtFecha.format(ini)} – ${fmtHora.format(fin)}`),
        el("td", "pequeno", (a.plantilla || "").split(":").pop()), tdEstado, tdVer);
      tbody.append(tr, fila_msg);
    });
    tabla.append(thead, tbody);
    const env = el("div", "tabla-envoltura");
    env.style.cssText = "border:none;border-radius:0";
    env.append(tabla);
    carta.append(cab, env);
    columna.append(carta);
  }


  /* --------------------------------------------------------- 3. bandeja */
  function ajustarBandeja() {
    if (!location.hash.startsWith("#/bandeja")) return;
    const contenido = document.getElementById("contenido");
    // detenidos: el portal cuenta como «detenido» todo caso sin compuerta pendiente, incluidos los
    // cerrados y los que no entraron a la lista. Se muestran por defecto solo los que esperan revisión.
    const tabla = [...contenido.querySelectorAll("table")].find((t) => esTablaDetenidos(t) && t.dataset.rol3 === "1");
    if (tabla && !tabla.dataset.rol3Preset) {
      tabla.dataset.rol3Preset = "1";
      tabla.rol3Filtrar?.("Estado", "pendiente revision");
      const revision = [...tabla.querySelectorAll("tbody tr")].filter((tr) => valorCelda(tr.children[1]) === "pendiente revision").length;
      const carta = tabla.closest(".carta");
      const h4 = carta?.querySelector(".carta-cabecera h4");
      if (h4) h4.firstChild.textContent = `Detenidos para revisión humana (${revision})`;
      const p = carta?.querySelector(".carta-cabecera p");
      if (p) p.textContent = "Casos que el grafo detuvo antes de una compuerta humana. Quite el filtro de estado " +
        "para ver también los cerrados y los que no entraron a la lista.";
      for (const st of contenido.querySelectorAll(".stat")) {
        if (norm(st.querySelector(".stat-etiqueta")?.textContent) !== "detenidos") continue;
        const v = st.querySelector(".stat-valor"), nota = st.querySelector(".stat-nota");
        if (v) v.textContent = revision;
        if (nota) nota.textContent = "esperan revisión humana";
      }
    }
    // compuerta 2: varios mensajes largos → desplazamiento interno y búsqueda por CV
    const h4c2 = [...contenido.querySelectorAll("h4")].find((x) => x.textContent.startsWith("Compuerta 2"));
    const lista = h4c2?.parentElement?.nextElementSibling;
    if (lista && !lista.dataset.rol3) {
      lista.dataset.rol3 = "1";
      if (lista.children.length > 1) {
        lista.classList.add("rol3-scroll-cartas");
        const buscar = Object.assign(document.createElement("input"), { type: "search", placeholder: "Buscar CV…",
          className: "rol3-buscar" });
        buscar.setAttribute("aria-label", "Buscar mensaje por CV");
        buscar.addEventListener("input", () => {
          [...lista.children].forEach((c) => { c.hidden = !norm(c.querySelector("h4")?.textContent).includes(norm(buscar.value)); });
        });
        h4c2.parentElement.append(buscar);
      }
    }
  }

  /* ------------------------------------------------------------ 4. textos */
  function limpiarTextos(raiz) {
    raiz.querySelectorAll(".aviso, .carta-cabecera p, .stat-nota, p").forEach((n) => {
      if (n.dataset.rol3Txt) return;
      n.dataset.rol3Txt = "1";
      const w = document.createTreeWalker(n, NodeFilter.SHOW_TEXT);
      for (let t = w.nextNode(); t; t = w.nextNode()) {
        const limpio = t.nodeValue.replace(/`([^`]+)`/g, "$1").replace(/\s*\(hallazgo H-\d+\)/g, "");
        if (limpio !== t.nodeValue) t.nodeValue = limpio;
      }
    });
  }

  /* ------------------------------------------------------------- arranque */
  function revisar(raiz = document) {
    raiz.querySelectorAll("table").forEach((t) => {
      if (t.dataset.rol3) return;
      if (esTablaCandidatos(t) || esTablaDetenidos(t) || esTablaAgenda(t)) mejorarTabla(t);
      else if (esTablaEvidencia(t)) {
        t.dataset.rol3 = "pendiente";
        cargarCvPorCaso().then(() => { anotarEvidencia(t); delete t.dataset.rol3; mejorarTabla(t); });
      }
    });
    corregirEstado(raiz);
    pintarAgenda();
    ajustarBandeja();
    limpiarTextos(document.getElementById("contenido") || raiz);
  }
  new MutationObserver(() => revisar()).observe(document.body, { childList: true, subtree: true });
  revisar();
})();

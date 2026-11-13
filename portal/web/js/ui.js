/* ============================================================================
   CVAgent · Utilidades de interfaz
   ----------------------------------------------------------------------------
   Hyperscript mínimo, iconos, avisos y formateo. Sin librerías externas: el
   proyecto no necesita un paso de compilación y arranca con un solo comando.
   ========================================================================== */

/** Crea un elemento. h("div.carta", {onclick}, hijos...) */
export function h(selector, props = {}, ...hijos) {
  const [etiqueta, ...clases] = selector.split(".");
  const el = document.createElement(etiqueta || "div");
  if (clases.length) el.className = clases.join(" ");

  for (const [k, v] of Object.entries(props || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className += (el.className ? " " : "") + v;
    else if (k === "html") el.innerHTML = v;                 // solo con texto ya escapado
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2), v);
    else if (k in el && k !== "list") el[k] = v;
    else el.setAttribute(k, v);
  }
  agregar(el, hijos);
  return el;
}

function agregar(padre, hijos) {
  for (const hijo of hijos.flat(Infinity)) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    padre.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
}

export const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const $ = (sel, raiz = document) => raiz.querySelector(sel);

export function vaciar(nodo) { while (nodo.firstChild) nodo.removeChild(nodo.firstChild); }

/* ------------------------------------------------------------------ iconos */
const RUTAS = {
  panel:    "M3 3h7v7H3zM14 3h7v4h-7zM14 10h7v11h-7zM3 13h7v8H3z",
  vacante:  "M3 7h18v13H3zM8 7V5a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M3 12h18",
  cv:       "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h4",
  motor:    "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.6 1.6 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.6 1.6 0 0 0-1.8-.3 1.6 1.6 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.6 1.6 0 0 0 9 19.4a1.6 1.6 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.6 1.6 0 0 0 .3-1.8 1.6 1.6 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.6 1.6 0 0 0 4.6 9a1.6 1.6 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.6 1.6 0 0 0 1.8.3H9a1.6 1.6 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.6 1.6 0 0 0 1 1.5 1.6 1.6 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.6 1.6 0 0 0-.3 1.8V9a1.6 1.6 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.6 1.6 0 0 0-1.5 1z",
  bandeja:  "M22 11.1V12a10 10 0 1 1-5.9-9.1M22 4 12 14.01l-3-3",
  escudo:   "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
  check:    "M20 6 9 17l-5-5",
  equis:    "M18 6 6 18M6 6l12 12",
  alerta:   "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  info:     "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  subir:    "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  bajar:    "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  mas:      "M12 5v14M5 12h14",
  basura:   "M3 6h18M8 6V4a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v2M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6",
  reloj:    "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 6v6l4 2",
  sol:      "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  luna:     "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  vacio:    "M20 7 12 3 4 7m16 0-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4",
  rayo:     "M13 2 3 14h9l-1 8 10-12h-9z",
  candado:  "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4",
};

export function icono(nombre, props = {}) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("fill", "none");
  svg.setAttribute("stroke", "currentColor");
  svg.setAttribute("stroke-width", props.grosor || "1.8");
  svg.setAttribute("stroke-linecap", "round");
  svg.setAttribute("stroke-linejoin", "round");
  svg.setAttribute("aria-hidden", "true");
  if (props.class) svg.setAttribute("class", props.class);
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", RUTAS[nombre] || RUTAS.info);
  svg.append(path);
  return svg;
}

/* ------------------------------------------------------------------ toast */
export function toast(mensaje, { titulo = "", tipo = "ok", ms = 4800 } = {}) {
  const cont = $("#toasts");
  const t = h(`div.toast.${tipo}`, {},
    icono({ ok: "check", alerta: "alerta", peligro: "equis", info: "info" }[tipo] || "info"),
    h("div.crece", {}, titulo && h("strong", {}, titulo), h("span", {}, mensaje)),
    h("button.cerrar", { onclick: () => t.remove(), "aria-label": "Cerrar" }, "×"));
  cont.append(t);
  if (ms) setTimeout(() => t.remove(), ms);
  return t;
}

/* ------------------------------------------------------------------ modal */
export function modal({ titulo, cuerpo, acciones = [], ancho }) {
  const fondo = h("div.modal-fondo", {
    onclick: (e) => { if (e.target === fondo) cerrar(); },
  });
  const cerrar = () => { fondo.remove(); document.removeEventListener("keydown", alTecla); };
  const alTecla = (e) => { if (e.key === "Escape") cerrar(); };
  document.addEventListener("keydown", alTecla);

  const caja = h("div.modal", ancho ? { style: `width:min(${ancho},100%)` } : {},
    h("div.carta-cabecera", {},
      h("h3", {}, titulo),
      h("button.btn.btn-fantasma.btn-icono", { onclick: cerrar, "aria-label": "Cerrar" }, icono("equis"))),
    h("div.carta-cuerpo", {}, cuerpo),
    acciones.length && h("div.carta-pie", {},
      h("div.crece"),
      ...acciones.map((a) =>
        h(`button.btn${a.estilo ? "." + a.estilo : ""}`, {
          onclick: () => a.alPulsar?.(cerrar), disabled: a.deshabilitado,
        }, a.texto))));

  fondo.append(caja);
  document.body.append(fondo);
  return { cerrar, caja };
}

export function confirmar({ titulo, mensaje, textoOk = "Confirmar", estiloOk = "btn-peligro" }) {
  return new Promise((resolver) => {
    modal({
      titulo,
      cuerpo: h("p.sin-margen.apagado", {}, mensaje),
      acciones: [
        { texto: "Cancelar", alPulsar: (c) => { c(); resolver(false); } },
        { texto: textoOk, estilo: estiloOk, alPulsar: (c) => { c(); resolver(true); } },
      ],
    });
  });
}

/* -------------------------------------------------------------- formateo */
export const pct = (n) => `${Math.round((n ?? 0) * 100)}%`;
export const fit = (n) => (n ?? 0).toFixed(2);

export function fecha(iso, conHora = true) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return String(iso).slice(0, conHora ? 16 : 10).replace("T", " ");
  return d.toLocaleString("es-CO", {
    day: "2-digit", month: "short", year: "numeric",
    ...(conHora ? { hour: "2-digit", minute: "2-digit" } : {}),
  });
}

export function horas(n) {
  if (n === null || n === undefined) return "—";
  if (n <= 0) return "vencido";
  if (n < 1) return `${Math.round(n * 60)} min`;
  if (n < 48) return `${Math.round(n)} h`;
  return `${Math.round(n / 24)} d`;
}

/* ------------------------------------------------------------ fragmentos */
export const pastilla = (texto, tipo = "neutra", conPunto = false) =>
  h(`span.pastilla.pastilla-${tipo}`, {}, conPunto && h("span.punto"), texto);

export const aviso = (texto, tipo = "info", titulo = "") =>
  h(`div.aviso.aviso-${tipo}`, {},
    icono({ ok: "check", alerta: "alerta", peligro: "alerta", info: "info" }[tipo] || "info"),
    h("div", {}, titulo && h("strong", {}, titulo + " "), texto));

export const stat = (etiqueta, valor, nota, tipo) => {
  // Un codigo largo no cabe al tamaño grande: se reduce en vez de desbordarse.
  const largo = String(valor).length > 11;
  return h("div.carta", {}, h("div.stat", {},
    h("div.stat-etiqueta", {}, etiqueta),
    h(`div.stat-valor${largo ? ".stat-valor-largo" : ""}`,
      tipo ? { style: `color:var(--${tipo})` } : {}, valor),
    nota && h("div.stat-nota", {}, nota)));
};

export const vacio = (titulo, texto, accion) =>
  h("div.vacio", {}, icono("vacio"), h("h4", {}, titulo), h("p", {}, texto), accion);

export const campo = (etiqueta, control, ayuda) =>
  h("div.campo", {}, h("label", {}, etiqueta), control, ayuda && h("span.ayuda", {}, ayuda));

export function medidor(valor, tipo = "marca") {
  return h("div.medidor", {},
    h("div", { style: `width:${Math.max(0, Math.min(1, valor)) * 100}%;background:var(--${tipo})` }));
}

export const cargando = (texto = "Cargando…") =>
  h("div.vacio", {}, h("span.cargando"), h("p", { style: "margin-top:12px" }, texto));

/* -------------------------------------------------- resaltado de citas */
/**
 * Pinta el CV con las citas marcadas en la posición exacta que indica el
 * extractor. Una cita cuyos offsets no recorten su propio texto se descarta
 * y se reporta: es un defecto del extractor, no de la interfaz.
 */
export function cvResaltado(texto, citas = []) {
  const validas = citas
    .filter((c) => texto.slice(c.inicio, c.fin) === c.texto)
    .sort((a, b) => a.inicio - b.inicio);

  const cont = h("div.lector");
  let cursor = 0;
  for (const c of validas) {
    if (c.inicio < cursor) continue;                       // solapada
    cont.append(document.createTextNode(texto.slice(cursor, c.inicio)));
    cont.append(h("mark.cita", {
      title: `campo: ${c.campo} · posición ${c.inicio}–${c.fin}`,
      dataset: { campo: c.campo },
    }, c.texto));
    cursor = c.fin;
  }
  cont.append(document.createTextNode(texto.slice(cursor)));
  return { nodo: cont, validas: validas.length, rotas: citas.length - validas.length };
}

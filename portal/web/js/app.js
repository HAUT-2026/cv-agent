/* ============================================================================
   CVAgent · Portal (Rol 4) — navegación y vistas
   ----------------------------------------------------------------------------
   El frontend pinta y recoge; no decide nada. Toda la lógica vive en el
   backend, sobre los contratos del Rol 1 y el motor de reglas del Rol 2.
   ========================================================================== */
import { api } from "./api.js";
import {
  $, h, icono, toast, vaciar, pastilla, aviso, stat, vacio, cargando,
  campo, medidor, confirmar, cvResaltado, fecha, pct, fit,
} from "./ui.js";

const sesion = {
  usuario: localStorage.getItem("cvagent.usuario") || "reclutador@grupo3.edu.co",
};

/* Las citas del Rol 1 son CitationRef; el resaltador usa {campo,texto,inicio,fin}. */
const citasUI = (citas = []) => citas.map((c) => ({
  campo: c.fuente, texto: c.cita, inicio: c.offset_inicio, fin: c.offset_fin,
}));

const ESTADO_TIPO = {
  cerrado: "ok", lista_aprobada: "ok", lista_ajustada: "ok",
  pendiente_aprobacion_lista: "alerta", pendiente_aprobacion_mensaje: "alerta",
  pendiente_revision: "alerta", lista_rechazada: "peligro",
  mensaje_rechazado: "peligro", pausado_kill_switch: "peligro",
  vencido_lista: "peligro", vencido_mensaje: "peligro",
};
const VEREDICTO_TIPO = {
  aprobado: "ok", bloqueado: "peligro",
  requiere_revision: "alerta", no_evaluable: "neutra",
};

/* ================================================================== Lote */
async function vistaLote() {
  const e = await api.estado();

  const metricas = h("div.rejilla.rejilla-4", {},
    stat("Vacante", e.cargado ? e.vacante_id : "—", e.cargado ? `versión v${e.vacante_version}` : "sin cargar"),
    stat("Evaluables", e.cargado ? e.evaluables : "—", e.cargado ? `de 40 hojas de vida` : null),
    stat("Casos corridos", e.corridos ?? 0),
    stat("Esperando aprobación", e.pendientes_aprobacion ?? 0, null,
      e.pendientes_aprobacion ? "alerta" : null));

  const acciones = h("div.carta", {},
    h("div.carta-cabecera", {}, h("h3", {}, "Correr el lote")),
    h("div.carta-cuerpo.columna", { style: "gap:14px" },
      h("p.pequeno.apagado.sin-margen", {},
        "Cargar lee la vacante vigente (R8) y aplica el motor del Rol 2 a los 40 CV: " +
        "R12 duplicados, R1 consentimiento, R2 formato, R11 experiencia efectiva, " +
        "R3 requisitos excluyentes y R7 anonimización. Ejecutar corre el grafo del " +
        "Rol 1 por caso hasta la primera compuerta humana."),
      h("div.fila", {},
        boton("Cargar lote", "rayo", "btn-primario", async () => {
          const r = await api.cargar();
          toast(`${r.evaluables} evaluables de ${r.cv_totales}. Rutas: ` +
                Object.entries(r.rutas).map(([k, v]) => `${k} ${v}`).join(", "),
                { titulo: `${r.vacante_id} v${r.vacante_version}`, tipo: "ok", ms: 9000 });
          navegar();
        }),
        boton("Ejecutar pipeline", "motor", "", async () => {
          const r = await api.ejecutar();
          toast(`${r.casos_corridos} casos, ${r.con_interrupcion} esperando aprobación.`,
                { titulo: "Propuesta lista", tipo: "ok" });
          if (r.errores.length) {
            r.errores.forEach((x) => toast(`${x.cv_id}: ${x.error}`, { tipo: "peligro", ms: 11000 }));
          }
          location.hash = "#/bandeja";
        }, !e.cargado))));

  const sistema = h("div.carta", {},
    h("div.carta-cabecera", {}, h("h3", {}, "Estado del sistema")),
    h("div.carta-cuerpo.columna", {},
      linea("Motor de reglas R1–R13", pastilla("real · Rol 2", "ok", true),
        "reglas/ sin modificar: funciones puras con 132 pruebas propias."),
      linea("Grafo, estado y decision_log", pastilla("real · Rol 1", "ok", true),
        `cvagent/ con checkpointer de ${e.checkpointer ?? "—"} y dos interrupciones humanas.`),
      linea("Registro encadenado",
        pastilla(e.cadena_integra === false ? "cadena rota" : "cadena íntegra",
          e.cadena_integra === false ? "peligro" : "ok", true),
        `${e.entradas_log ?? 0} entrada(s) con hash encadenado.`),
      linea("Analista y auditor", pastilla("provisional · Rol 4", "alerta", true),
        "Sin modelo de lenguaje: anclan citas por posición en el texto canónico. " +
        "Son el hueco del Rol 3 y producen ya los contratos definitivos."),
      linea("Portal, calendario, correo y ATS", pastilla("simulados", "alerta", true),
        "SimulatedDeliveryGateway del Rol 1, con clave de idempotencia.")));

  const rutas = e.cargado && e.staging ? h("div.carta", {},
    h("div.carta-cabecera", {}, h("h3", {}, "Staging del lote"),
      pastilla(`R5 ${e.staging.empate_r5 ? "empate" : "sin empate"}`,
        e.staging.empate_r5 ? "alerta" : "neutra")),
    h("div.carta-cuerpo", {},
      h("dl.lista-datos", {},
        h("dt", {}, "Identificador"), h("dd", {}, h("code", {}, e.staging.staging_id)),
        h("dt", {}, "Propuestos"), h("dd", {}, e.staging.top.length),
        h("dt", {}, "Diferencia 5.º–6.º"), h("dd", {}, e.staging.diferencia_5_6 ?? "—"),
        h("dt", {}, "A revisión por R4"), h("dd", {},
          e.staging.revision_humana_r4.join(", ") || "ninguno")),
      e.staging.aviso_r6 && aviso(e.staging.aviso_r6, "alerta", "R6."))) : null;

  return h("div.columna", { style: "gap:22px" },
    metricas,
    !e.cargado && aviso("Todavía no hay lote cargado. Use «Cargar lote» para empezar.",
      "info", "Primer uso."),
    h("div.rejilla.rejilla-2", { style: "align-items:start" },
      h("div.columna", { style: "gap:18px" }, acciones, rutas),
      sistema));
}

function linea(etiqueta, insignia, nota) {
  return h("div", {},
    h("div.fila.fila-sep", {}, h("strong.pequeno", {}, etiqueta), insignia),
    h("p.diminuto.apagado.sin-margen", {}, nota));
}

function boton(texto, ic, clase, accion, deshabilitado = false) {
  const b = h(`button.btn${clase ? "." + clase : ""}`, {
    disabled: deshabilitado,
    onclick: async () => {
      b.disabled = true;
      const original = [...b.childNodes];
      b.replaceChildren(h("span.cargando"), document.createTextNode(" " + texto));
      try { await accion(); }
      catch (err) { toast(err.message, { titulo: "No se pudo", tipo: "peligro", ms: 9000 }); }
      finally { b.disabled = deshabilitado; b.replaceChildren(...original); }
    },
  }, icono(ic), texto);
  return b;
}

/* =========================================================== Candidatos */
async function vistaCandidatos() {
  const lista = await api.candidatos();
  if (!lista.length) {
    return h("div.carta", {}, vacio("Sin candidatos evaluables",
      "Cargue y ejecute el lote desde la vista Lote.",
      h("button.btn", { onclick: () => (location.hash = "#/lote") }, "Ir a Lote")));
  }

  const detalle = h("div");
  const pintarDetalle = async (cv) => {
    detalle.replaceChildren(cargando("Cargando el texto canónico…"));
    detalle.replaceChildren(await panelEvidencia(cv));
  };

  const filas = lista.map((c) => h("tr", {
    style: "cursor:pointer", onclick: () => pintarDetalle(c),
  },
    h("td.num", {}, c.posicion ?? "—"),
    h("td", {}, h("strong.mono", {}, c.cv_id)),
    h("td", {}, h("code.tenue", { title: c.candidato_ref }, c.candidato_ref.slice(0, 14))),
    h("td.num", {}, fit(c.puntaje)),
    h("td", { style: "min-width:120px" },
      h("div.fila", { style: "gap:8px" },
        medidor(c.cobertura, c.cobertura >= 0.7 ? "ok" : "peligro"),
        h("span.diminuto.nowrap", {}, pct(c.cobertura)))),
    h("td", {}, c.veredicto
      ? pastilla(c.veredicto.estado, VEREDICTO_TIPO[c.veredicto.estado] || "neutra", true)
      : h("span.tenue", {}, "—")),
    h("td", {}, pastilla((c.estado_caso || "—").replace(/_/g, " "),
      ESTADO_TIPO[c.estado_caso] || "neutra")),
    h("td", {}, pastilla(c.procedencia === "pdf" ? "PDF" : "gemelo JSON",
      c.procedencia === "pdf" ? "neutra" : "alerta"))));

  const tabla = h("div.carta", {},
    h("div.carta-cabecera", {},
      h("div.crece", {},
        h("h4.sin-margen", {}, `Evaluables (${lista.length})`),
        h("p.diminuto.apagado.sin-margen", {},
          "Orden por posición en el staging; los que no entran al Top van después. " +
          "Haga clic en una fila para ver la evidencia."))),
    h("div.tabla-envoltura", { style: "border:none;border-radius:0" },
      h("table", {},
        h("thead", {}, h("tr", {},
          ...["#", "CV", "Referencia", "Puntaje", "Cobertura", "Veredicto", "Estado", "Fuente"]
            .map((t) => h("th", {}, t)))),
        h("tbody", {}, ...filas))));

  pintarDetalle(lista[0]);
  return h("div.columna", { style: "gap:18px" },
    aviso("La referencia opaca `cand_…` es lo único que ven el grafo y el modelo: " +
      "R7 enmascara nombre, documento, contacto y proxies antes de evaluar.", "info",
      "Anonimización."),
    tabla, detalle);
}

async function panelEvidencia(c) {
  const doc = await api.texto(c.cv_id);
  const { nodo, validas, rotas } = cvResaltado(doc.texto, citasUI(doc.citas));

  const requisitos = Object.entries(c.estado_requisitos || {}).map(([id, estado]) =>
    h("div.regla", {},
      h("div", { class: `regla-marca ${estado === "cumple" ? "si" : "no"}` },
        icono(estado === "cumple" ? "check" : "equis")),
      h("div.regla-texto", {},
        h("strong", {}, id), h("br"),
        h("span.pequeno", {}, estado.replace(/_/g, " ")))));

  return h("div.carta", {},
    h("div.carta-cabecera", {},
      h("div.crece", {},
        h("h4.sin-margen", {}, c.cv_id),
        h("p.diminuto.apagado.sin-margen", {},
          `${c.candidato_ref} · puntaje ${fit(c.puntaje)} · cobertura ${pct(c.cobertura)} · ` +
          `${c.meses_efectivos ?? "—"} meses efectivos (R11)`)),
      c.veredicto && pastilla(c.veredicto.estado,
        VEREDICTO_TIPO[c.veredicto.estado] || "neutra", true)),
    h("div.carta-cuerpo", {},
      c.veredicto && aviso(c.veredicto.razon,
        c.veredicto.estado === "aprobado" ? "info" : "alerta"),
      h("div.rejilla", { style: "grid-template-columns:1fr 280px;gap:18px;align-items:start" },
        h("div", {},
          rotas > 0 && aviso(
            `${rotas} cita(s) con offsets que no recortan su propio texto. Es un ` +
            "defecto del extractor: el auditor no puede verificarlas.",
            "peligro", "Evidencia inválida."),
          nodo,
          h("p.diminuto.apagado", { style: "margin:10px 0 0" },
            `${validas} de ${doc.citas.length} citas verificadas recortando el texto ` +
            `canónico por posición. Fuente: ${doc.procedencia === "pdf" ? "PDF" : "gemelo JSON"}.`)),
        h("div", {},
          h("div.diminuto.apagado", { style: "margin-bottom:6px" }, "REQUISITOS (R3)"),
          ...requisitos))));
}

/* ============================================================== Bandeja */
async function vistaBandeja() {
  const [estado, lista, parados] = await Promise.all(
    [api.estado(), api.candidatos(), api.detenidos()]);

  if (!estado.cargado || !estado.staging) {
    return h("div.carta", {}, vacio("No hay propuesta",
      "Cargue y ejecute el lote para generar una lista corta que revisar.",
      h("button.btn", { onclick: () => (location.hash = "#/lote") }, "Ir a Lote")));
  }

  const yaDecidida = Boolean(estado.decision_lista);
  const pendientesMensaje = lista.filter(
    (c) => c.interrupcion && c.interrupcion.tipo === "mensaje_exacto");

  return h("div.columna", { style: "gap:22px" },
    h("div.rejilla.rejilla-3", {},
      stat("Propuestos", estado.staging.top.length, `staging ${estado.staging.staging_id}`),
      stat("Evaluables", estado.evaluables),
      stat("Compuerta 1", yaDecidida ? estado.decision_lista.decision : "pendiente", "lista corta",
        yaDecidida ? "ok" : "alerta"),
      stat("Compuerta 2", pendientesMensaje.length, "mensajes por aprobar",
        pendientesMensaje.length ? "alerta" : null),
      stat("Detenidos", parados.length, "bloqueados por el auditor",
        parados.length ? "peligro" : null)),

    yaDecidida ? null : compuertaLista(estado, lista),
    yaDecidida ? resumenDecision(estado) : null,
    pendientesMensaje.length ? compuertaMensaje(pendientesMensaje) : null,
    parados.length ? panelDetenidos(parados) : null);
}

function compuertaLista(estado, lista) {
  const top = estado.staging.top;
  const seleccion = new Map(top.map((t) => [t.cv_id, true]));
  const porCv = Object.fromEntries(lista.map((c) => [c.cv_id, c]));

  const tarjetas = h("div.columna", { style: "gap:10px" });
  const pintar = () => tarjetas.replaceChildren(...top.map((t) => {
    const c = porCv[t.cv_id] || {};
    const bloqueado = c.veredicto?.estado === "bloqueado";
    if (bloqueado) seleccion.set(t.cv_id, false);
    return h("div.carta", {}, h("div.carta-cuerpo", { style: "padding:14px 16px" },
      h("div.fila", { style: "align-items:flex-start;gap:12px" },
        h("div.crece", {},
          h("div.fila", { style: "gap:8px;align-items:baseline" },
            h("strong", {}, `${t.posicion}.`), h("strong.mono", {}, t.cv_id),
            h("span.tenue.diminuto", {}, `puntaje ${fit(t.puntaje)} · cobertura ${pct(t.cobertura)}`)),
          c.veredicto && h("div", { style: "margin-top:6px" },
            pastilla(c.veredicto.estado, VEREDICTO_TIPO[c.veredicto.estado] || "neutra", true))),
        h(`label.casilla${bloqueado ? ".deshabilitada" : ""}`, {
          title: bloqueado ? "El auditor lo bloqueó: no se puede incluir" : "Incluir en la lista aprobada",
        },
          h("input", {
            type: "checkbox", checked: seleccion.get(t.cv_id), disabled: bloqueado,
            onchange: (ev) => { seleccion.set(t.cv_id, ev.target.checked); actualizar(); },
          }),
          h("span.pequeno", {}, "incluir"))),
      c.veredicto && c.veredicto.estado !== "aprobado" &&
        h("p.diminuto.sin-margen", { style: "margin-top:8px;color:var(--peligro)" },
          c.veredicto.razon)));
  }));

  const resumen = h("div");
  const razon = h("input", { type: "text", value: "Lista corta revisada contra la evidencia" });
  const pie = h("div.carta-pie");

  const actualizar = () => {
    const elegidos = [...seleccion].filter(([, v]) => v).map(([k]) => k);
    const ajustada = elegidos.length !== top.length;
    resumen.replaceChildren(
      h("div.diminuto.apagado", { style: "margin-bottom:5px" }, "SELECCIÓN ACTUAL"),
      elegidos.length
        ? h("div.fila", { style: "flex-wrap:wrap;gap:5px" },
            ...elegidos.map((x) => pastilla(x, "marca")))
        : h("span.tenue.pequeno", {}, "ninguno"));

    const enviar = async (decision) => {
      if (decision === "rechazar" && !await confirmar({
        titulo: "Rechazar la lista completa",
        mensaje: "Todos los casos del lote reciben una decisión de rechazo con su razón. " +
                 "No se agenda ninguna entrevista.",
        textoOk: "Rechazar",
      })) return;
      const cuerpo = {
        decision, aprobador: sesion.usuario, razon: razon.value.trim() || "Sin comentario",
        cv_ids_aprobados: decision === "ajustar" ? elegidos : null,
      };
      const r = await api.decidirLista(cuerpo);
      toast(`${r.aprobados.length} aprobado(s), ${r.reanudados.length} caso(s) con decisión registrada.`,
        { titulo: "Compuerta 1 resuelta", tipo: "ok" });
      navegar();
    };

    pie.replaceChildren(
      h("button.btn.btn-primario", {
        disabled: ajustada || !elegidos.length,
        title: ajustada ? "La selección cambió: use «Ajustar y aprobar»" : "",
        onclick: () => enviar("aprobar"),
      }, icono("check"), "Aprobar la propuesta"),
      h("button.btn", {
        disabled: !ajustada || !elegidos.length, onclick: () => enviar("ajustar"),
      }, "Ajustar y aprobar"),
      h("div.crece"),
      h("button.btn.btn-peligro", { onclick: () => enviar("rechazar") },
        icono("equis"), "Rechazar la lista"));
  };

  pintar(); actualizar();

  return h("div.carta", {},
    h("div.carta-cabecera", {},
      h("div.crece", {},
        h("h4.sin-margen", {}, "Compuerta 1 · Aprobación de la lista corta"),
        h("p.diminuto.apagado.sin-margen", {},
          "La decisión se reparte a cada hilo del grafo: aprobar a los que entran y " +
          "rechazar al resto, siempre con razón. Ningún silencio cuenta como aprobación."))),
    h("div.carta-cuerpo.columna", { style: "gap:16px" },
      tarjetas, resumen, campo("Razón que queda en el registro", razon)),
    pie);
}

function panelDetenidos(parados) {
  return h("div.carta", {},
    h("div.carta-cabecera", {},
      h("div.crece", {},
        h("h4.sin-margen", {}, `Detenidos antes de la compuerta (${parados.length})`),
        h("p.diminuto.apagado.sin-margen", {},
          "El grafo los paró porque el auditor los bloqueó, así que no generan " +
          "aprobación pendiente. No son un descarte: necesitan revisión humana y " +
          "por eso se muestran aquí (hallazgo H-5).")),
      pastilla("revisión humana", "alerta", true)),
    h("div.tabla-envoltura", { style: "border:none;border-radius:0" },
      h("table", {},
        h("thead", {}, h("tr", {},
          ...["CV", "Estado", "Razón de parada", "Veredicto del auditor"]
            .map((t) => h("th", {}, t)))),
        h("tbody", {}, ...parados.map((c) => h("tr", {},
          h("td", {}, h("strong.mono", {}, c.cv_id)),
          h("td", {}, pastilla((c.estado_caso || "—").replace(/_/g, " "),
            ESTADO_TIPO[c.estado_caso] || "neutra")),
          h("td.pequeno", {}, (c.razon_parada || "—").replace(/_/g, " ")),
          h("td.pequeno", {}, c.veredicto?.razon || "—")))))));
}

function resumenDecision(estado) {
  const d = estado.decision_lista;
  return h("div.carta", {},
    h("div.carta-cabecera", {},
      h("h4.crece.sin-margen", {}, "Compuerta 1 · resuelta"),
      pastilla(d.decision, d.decision === "rechazar" ? "peligro" : "ok", true)),
    h("div.carta-cuerpo", {},
      h("dl.lista-datos", {},
        h("dt", {}, "Aprobador"), h("dd", {}, d.aprobador),
        h("dt", {}, "Razón"), h("dd", {}, d.razon),
        h("dt", {}, "Momento"), h("dd", {}, fecha(d.momento)),
        h("dt", {}, "Aprobados"), h("dd", {}, d.aprobados.join(", ") || "ninguno"))));
}

function compuertaMensaje(pendientes) {
  const contenedor = h("div.columna", { style: "gap:12px" });

  const pintar = () => contenedor.replaceChildren(...pendientes.map((c) => {
    const propuesta = c.interrupcion.propuesta || {};
    const texto = h("textarea", { style: "min-height:130px" }, propuesta.texto_exacto || "");
    const razon = h("input", { type: "text", value: "Texto revisado" });

    const enviar = async (decision) => {
      const cuerpo = {
        cv_id: c.cv_id, decision, aprobador: sesion.usuario,
        razon: razon.value.trim() || "Sin comentario",
        texto_exacto: decision === "ajustar" ? texto.value : null,
      };
      const r = await api.decidirMensaje(cuerpo);
      toast(`${c.cv_id}: ${r.estado.replace(/_/g, " ")}` +
            (r.efectos_externos ? ` · ${r.efectos_externos} efecto(s) ejecutado(s)` : ""),
            { titulo: "Compuerta 2 resuelta", tipo: "ok" });
      navegar();
    };

    return h("div.carta", {},
      h("div.carta-cabecera", {},
        h("div.crece", {},
          h("h4.sin-margen", {}, c.cv_id),
          h("p.diminuto.apagado.sin-margen", {},
            `franja ${propuesta.franja || "—"} · plantilla ${propuesta.plantilla_version || "—"}`)),
        pastilla("mensaje exacto", "alerta", true)),
      h("div.carta-cuerpo.columna", { style: "gap:12px" },
        campo("Texto que se enviará", texto,
          "Editarlo convierte la decisión en «ajustar»: el texto ajustado queda en el registro."),
        campo("Razón", razon)),
      h("div.carta-pie", {},
        h("button.btn.btn-primario", { onclick: () => enviar("aprobar") },
          icono("check"), "Aprobar y enviar"),
        h("button.btn", { onclick: () => enviar("ajustar") }, "Ajustar y enviar"),
        h("div.crece"),
        h("button.btn.btn-peligro", { onclick: () => enviar("rechazar") }, "Rechazar")));
  }));

  pintar();
  return h("div.columna", { style: "gap:12px" },
    h("div", {},
      h("h4", {}, "Compuerta 2 · Aprobación del mensaje exacto"),
      h("p.pequeno.apagado.sin-margen", {},
        "R10: ninguna comunicación sale sin aprobación registrada del texto y del " +
        "destinatario. El envío es simulado y tiene clave de idempotencia.")),
    contenedor);
}

/* ============================================================ Evidencia */
async function vistaEvidencia() {
  const reg = await api.evidencia();
  if (!reg.entradas.length) {
    return h("div.carta", {}, vacio("Sin registro todavía",
      "Cada paso del grafo y cada decisión humana quedan aquí, encadenados por hash."));
  }

  const casos = [...new Set(reg.entradas.map((e) => e.correlation_id))];
  const filtro = h("select", { style: "max-width:380px" },
    h("option", { value: "" }, `Todos los casos (${casos.length})`),
    ...casos.map((c) => h("option", { value: c }, c.slice(0, 18) + "…")));

  const cuerpo = h("tbody");
  const pintar = () => {
    const f = filtro.value;
    const filas = f ? reg.entradas.filter((e) => e.correlation_id === f) : reg.entradas;
    cuerpo.replaceChildren(...filas.map((e) => h("tr", {},
      h("td.nowrap", {}, fecha(e.tiempo)),
      h("td", {}, h("code.tenue", { title: e.correlation_id }, e.correlation_id.slice(0, 8))),
      h("td", {}, pastilla(e.componente, e.componente === "human-approval" ? "marca" : "neutra")),
      h("td.pequeno", {}, e.razon),
      h("td.pequeno", {}, e.aprobador || "—"),
      h("td", {}, e.veredicto
        ? pastilla(e.veredicto, VEREDICTO_TIPO[e.veredicto] || "neutra") : h("span.tenue", {}, "—")),
      h("td.num", {}, e.cobertura === null || e.cobertura === undefined ? "—" : pct(e.cobertura)),
      h("td", {}, h("code.tenue", { title: e.hash_entrada }, e.hash_entrada.slice(0, 10))))));
  };
  filtro.addEventListener("change", pintar);
  pintar();

  return h("div.columna", { style: "gap:20px" },
    h("div.rejilla.rejilla-3", {},
      stat("Entradas", reg.entradas.length),
      stat("Casos", casos.length),
      stat("Cadena", reg.integra ? "íntegra" : "rota",
        reg.integra ? "ninguna entrada fue alterada" : "el registro fue modificado",
        reg.integra ? "ok" : "peligro")),
    aviso("Cada entrada guarda el hash de la anterior. El registro lo escribe el " +
      "`DecisionLog` del Rol 1 y el checkpoint del grafo no lo reemplaza: son dos " +
      "cosas distintas, una para reanudar y otra para auditar.", "info", "Cómo funciona."),
    h("div.carta", {},
      h("div.carta-cabecera", {},
        h("h4.crece.sin-margen", {}, "Registro de decisiones"), filtro),
      h("div.tabla-envoltura", { style: "border:none;border-radius:0" },
        h("table", {},
          h("thead", {}, h("tr", {},
            ...["Momento", "Caso", "Componente", "Razón", "Aprobador", "Veredicto", "Cobertura", "Hash"]
              .map((t) => h("th", {}, t)))),
          cuerpo)),
      h("div.carta-pie", {},
        h("a.btn.btn-sm", { href: "/api/evidencia/csv" }, icono("bajar"), "Descargar CSV"))));
}

/* ========================================================== navegación */
const VISTAS = {
  lote:       { titulo: "Lote", sub: "Vacante vigente, motor de reglas y pipeline", icono: "motor", render: vistaLote },
  candidatos: { titulo: "Candidatos", sub: "Evaluables, evidencia citada y requisitos", icono: "cv", render: vistaCandidatos },
  bandeja:    { titulo: "Bandeja", sub: "Las dos compuertas humanas", icono: "bandeja", render: vistaBandeja },
  evidencia:  { titulo: "Evidencia", sub: "Registro encadenado de todo lo decidido", icono: "escudo", render: vistaEvidencia },
};

function aplicarTema(t) {
  if (t) { document.documentElement.dataset.tema = t; localStorage.setItem("cvagent.tema", t); }
  else { delete document.documentElement.dataset.tema; localStorage.removeItem("cvagent.tema"); }
  const b = $("#btn-tema");
  if (!b) return;
  vaciar(b);
  const oscuro = t === "oscuro" || (!t && matchMedia("(prefers-color-scheme: dark)").matches);
  b.append(icono(oscuro ? "sol" : "luna"));
  b.title = oscuro ? "Cambiar a modo claro" : "Cambiar a modo oscuro";
}

async function navegar() {
  const clave = (location.hash.replace("#/", "").split("?")[0]) || "lote";
  const vista = VISTAS[clave] || VISTAS.lote;
  document.querySelectorAll(".nav-item").forEach((a) =>
    a.classList.toggle("activo", a.dataset.vista === clave));
  $("#titulo").textContent = vista.titulo;
  $("#subtitulo").textContent = vista.sub;
  document.title = `${vista.titulo} · CVAgent`;

  const contenido = $("#contenido");
  vaciar(contenido);
  contenido.append(cargando());
  try {
    const nodo = await vista.render();
    vaciar(contenido);
    contenido.append(nodo);
    scrollTo({ top: 0 });
  } catch (e) {
    vaciar(contenido);
    contenido.append(h("div.carta", {}, h("div.carta-cuerpo", {},
      h("h3", { style: "color:var(--peligro)" }, "No se pudo cargar la vista"),
      h("p.apagado", {}, e.message || String(e)),
      h("button.btn", { onclick: navegar }, "Reintentar"))));
  }
}

function iniciar() {
  aplicarTema(localStorage.getItem("cvagent.tema"));
  const nav = $("#nav");
  for (const [clave, v] of Object.entries(VISTAS)) {
    nav.append(h("a.nav-item", { href: `#/${clave}`, dataset: { vista: clave } },
      icono(v.icono), h("span.etiqueta", {}, v.titulo)));
  }
  const entrada = $("#usuario-correo");
  entrada.value = sesion.usuario;
  $("#avatar").textContent = sesion.usuario.slice(0, 2).toUpperCase();
  entrada.addEventListener("change", () => {
    sesion.usuario = entrada.value.trim() || "reclutador@grupo3.edu.co";
    localStorage.setItem("cvagent.usuario", sesion.usuario);
    $("#avatar").textContent = sesion.usuario.slice(0, 2).toUpperCase();
  });
  $("#btn-tema").addEventListener("click", () => {
    const oscuro = document.documentElement.dataset.tema === "oscuro" ||
      (!localStorage.getItem("cvagent.tema") && matchMedia("(prefers-color-scheme: dark)").matches);
    aplicarTema(oscuro ? "claro" : "oscuro");
  });
  addEventListener("hashchange", navegar);
  if (!location.hash) location.hash = "#/lote";
  navegar();
}

document.addEventListener("DOMContentLoaded", iniciar);

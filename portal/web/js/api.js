/* Cliente de la API del portal. Único punto de acceso al backend. */

class ErrorApi extends Error {
  constructor(mensaje, estado) { super(mensaje); this.estado = estado; }
}

async function pedir(ruta, opciones = {}) {
  let r;
  try { r = await fetch(ruta, opciones); }
  catch { throw new ErrorApi("No se pudo contactar al servidor. ¿Está corriendo?", 0); }
  if (!r.ok) {
    let cuerpo = null;
    try { cuerpo = await r.json(); } catch { /* sin JSON */ }
    throw new ErrorApi(mensajeDeError(cuerpo, r.status), r.status);
  }
  return r.status === 204 ? null : r.json();
}

function mensajeDeError(cuerpo, estado) {
  const d = cuerpo?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => {
      const campo = (e.loc || []).filter((x) => x !== "body").join(".");
      return campo ? `${campo}: ${e.msg}` : e.msg;
    }).join(" · ");
  }
  return `Error ${estado}`;
}

const json = (metodo, cuerpo) => ({
  method: metodo,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(cuerpo),
});

export const api = {
  ErrorApi,
  estado:     () => pedir("/api/estado"),
  cargar:     (vacante_id = "VAC-001", version = null) =>
                pedir("/api/lote/cargar", json("POST", { vacante_id, version })),
  ejecutar:   () => pedir("/api/lote/ejecutar", { method: "POST" }),
  candidatos: () => pedir("/api/candidatos"),
  detenidos:  () => pedir("/api/detenidos"),
  texto:      (cvId) => pedir(`/api/candidatos/${cvId}/texto`),
  decidirLista:   (cuerpo) => pedir("/api/decision/lista", json("POST", cuerpo)),
  decidirMensaje: (cuerpo) => pedir("/api/decision/mensaje", json("POST", cuerpo)),
  evidencia:  () => pedir("/api/evidencia"),
};

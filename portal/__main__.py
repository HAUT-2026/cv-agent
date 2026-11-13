"""Arranque del portal:  python -m portal"""
from __future__ import annotations

import sys
import webbrowser
from threading import Timer

PUERTO = 8000


def main() -> None:
    try:
        import uvicorn
    except ImportError:
        print("Faltan dependencias del portal. Ejecute:\n"
              "    pip install -e '.[portal]'   (o: pip install fastapi uvicorn pdfplumber)")
        raise SystemExit(1)

    url = f"http://localhost:{PUERTO}"
    print(f"\n  CVAgent · Portal\n  Portal : {url}\n  API    : {url}/docs\n"
          "  (Ctrl+C para detener)\n")
    if "--sin-navegador" not in sys.argv:
        Timer(1.5, lambda: webbrowser.open(url)).start()
    uvicorn.run("portal.api:app", host="127.0.0.1", port=PUERTO,
                reload="--recargar" in sys.argv)


if __name__ == "__main__":
    main()

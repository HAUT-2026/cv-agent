"""Rol 3 — agentes de CVAgent (analista y auditor determinista; auditor LLM y agendador en construcción).

Módulos:
    criterios     Vacante y requisitos versionados (con equivalencias) que consumen los agentes.
    cv_json       CV en JSON del dataset → texto canónico (sin identidad; texto oculto bloqueado).
    texto         TextoCanonico y localización determinista de citas (offsets exactos).
    sanitizacion  Indicios de inyección y proxies de R7, con offsets.
    salida        Esquemas: FichaLLM (lo que llena el LLM), FichaCandidato, Veredicto, PropuestaAgenda.
    ficha         FichaLLM → FichaCandidato (verifica citas; no corrige al modelo).
    llm           Cliente agnóstico del proveedor (protocolo OpenAI chat + tools); config por LLM_*.
    herramientas  Herramientas de los agentes y registro central.
    agente        Motor razonar → actuar → observar, con allowlist, freno de bucles y traza.
    analista      Agente analista (prompt, allowlist, analizar_caso).
    auditor       Auditor determinista: Veredicto con hallazgos (severidad + offset); bloquea, no aprueba.
    evaluacion    Banco de evaluación contra data/manifiesto.json (solo para medir).

Ver docs/rol-3-agentes.md.
"""

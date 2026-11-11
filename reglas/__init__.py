"""Reglas y datos del caso (Rol 2). Ver README_ROL2.md."""
from .comun import HOY_REF, seudonimizar
from .diccionario import cargar_diccionario, consultar_equivalencias
from .vacantes import cargar_indice, cargar_vacante
from .reglas import (r1_consentimiento, r2_formato, r3_requisitos_excluyentes, r4_cobertura, r5_empate,
                     r6_tamano_lista, r7_anonimizar, r8_vigencia, r9_retencion, r10_doble_aprobacion,
                     r11_experiencia_efectiva, r12_deduplicar, r13_cambio_vacante)
from .motor import evaluar_caso, procesar_lote, armar_staging

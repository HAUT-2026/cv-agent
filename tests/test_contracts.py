from datetime import datetime, timezone
import uuid

import pytest
from pydantic import ValidationError

from cvagent.contracts import (
    CONTRACT_EXAMPLES,
    CONTRACT_VERSION,
    AuditMetadata,
    CaseState,
    CitationRef,
    FichaCandidato,
    RazónParada,
    contract_json_schemas,
    example_case_state,
)


def test_case_state_example_is_strict_and_versioned() -> None:
    state = example_case_state()

    assert state.correlation_id == CONTRACT_EXAMPLES["input"]["correlation_id"]
    assert state.contrato_version == CONTRACT_VERSION
    with pytest.raises(ValidationError):
        CaseState.model_validate(
            {
                **state.model_dump(),
                "unexpected": "must be rejected",
            }
        )


def test_citation_requires_exact_offsets_and_same_case() -> None:
    correlation_id = str(uuid.uuid4())
    citation = CitationRef(
        correlation_id=correlation_id,
        fuente="cv-sanitizado.txt",
        cita="Python",
        offset_inicio=8,
        offset_fin=14,
    )

    assert citation.verify_against("Perfil: Python experto").verificada is True
    with pytest.raises(ValueError, match="does not match"):
        citation.verify_against("Perfil: Django experto")


def test_ficha_rejects_bad_correlation_id_and_non_coherent_timestamps() -> None:
    now = datetime.now(timezone.utc)
    correlation_id = str(uuid.uuid4())
    audit = AuditMetadata(
        componente="test",
        fuente=["synthetic"],
        versiones={"vacante": "v1"},
        timestamp=now,
    )
    citation = CitationRef(
        correlation_id=correlation_id,
        fuente="synthetic.txt",
        cita="Python",
        offset_inicio=0,
        offset_fin=6,
    )
    with pytest.raises(ValidationError):
        FichaCandidato(
            correlation_id="not-a-uuid",
            candidato_ref="cand-demo",
            vacante_id="vac-demo",
            vacante_version="v1",
            resumen="Synthetic profile",
            citas=[citation],
            creado_en=now,
            actualizado_en=now,
            auditoria=audit,
        )


def test_contract_schemas_are_closed() -> None:
    schemas = contract_json_schemas()

    assert {"CaseState", "FichaCandidato", "Veredicto", "PropuestaAgenda", "EntradaDecisionLog"} <= schemas.keys()
    assert schemas["CaseState"]["additionalProperties"] is False
    assert RazónParada.APROBACION_LISTA_PENDIENTE.value == "aprobacion_lista_pendiente"

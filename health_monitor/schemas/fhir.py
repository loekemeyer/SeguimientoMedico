"""Mapeo a HL7 / FHIR R4 para interoperabilidad con prepagas y obras sociales.

Convierte un `ClinicalReadout` interno en recursos FHIR `Observation` estándar,
de modo que el sistema se acople como "enchufe" nativo a la HCE de OSDE, Swiss
Medical, PAMI, etc.

Se construyen los recursos como dicts (JSON FHIR) para no acoplar el proyecto a
una librería FHIR específica; el formato sigue FHIR R4 y usa códigos LOINC.
Referencias LOINC:
  - 85354-9  Panel de presión arterial
  - 8480-6   Presión sistólica
  - 8462-4   Presión diastólica
  - 8867-4   Frecuencia cardíaca
  - 2339-0   Glucosa en sangre
  - 59408-5  Saturación de oxígeno (SpO2)
  - 8310-5   Temperatura corporal
"""
from __future__ import annotations

from typing import Any

from health_monitor.schemas.clinical import ClinicalReadout

_UCUM = "http://unitsofmeasure.org"
_LOINC = "http://loinc.org"


def _observation(
    paciente_id: int, when: str, code: str, display: str,
    value: float, unit: str, ucum: str,
) -> dict[str, Any]:
    return {
        "resourceType": "Observation",
        "status": "final",
        "category": [{
            "coding": [{
                "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                "code": "vital-signs",
                "display": "Vital Signs",
            }]
        }],
        "code": {"coding": [{"system": _LOINC, "code": code, "display": display}]},
        "subject": {"reference": f"Patient/{paciente_id}"},
        "effectiveDateTime": when,
        "valueQuantity": {"value": value, "unit": unit, "system": _UCUM, "code": ucum},
    }


def readout_to_fhir_bundle(readout: ClinicalReadout) -> dict[str, Any]:
    """Convierte un ClinicalReadout en un Bundle FHIR de Observations.

    Solo incluye las métricas presentes (no `None`).
    """
    when = readout.timestamp.isoformat()
    pid = readout.paciente_id
    observations: list[dict[str, Any]] = []

    if readout.presion_sistolica is not None and readout.presion_diastolica is not None:
        # Panel de presión arterial con dos componentes (forma canónica FHIR).
        observations.append({
            "resourceType": "Observation",
            "status": "final",
            "category": [{
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                    "code": "vital-signs",
                }]
            }],
            "code": {"coding": [{"system": _LOINC, "code": "85354-9",
                                 "display": "Blood pressure panel"}]},
            "subject": {"reference": f"Patient/{pid}"},
            "effectiveDateTime": when,
            "component": [
                {"code": {"coding": [{"system": _LOINC, "code": "8480-6",
                                      "display": "Systolic blood pressure"}]},
                 "valueQuantity": {"value": readout.presion_sistolica, "unit": "mmHg",
                                   "system": _UCUM, "code": "mm[Hg]"}},
                {"code": {"coding": [{"system": _LOINC, "code": "8462-4",
                                      "display": "Diastolic blood pressure"}]},
                 "valueQuantity": {"value": readout.presion_diastolica, "unit": "mmHg",
                                   "system": _UCUM, "code": "mm[Hg]"}},
            ],
        })

    if readout.frecuencia_cardiaca is not None:
        observations.append(_observation(
            pid, when, "8867-4", "Heart rate",
            readout.frecuencia_cardiaca, "beats/min", "/min"))

    if readout.glucemia is not None:
        observations.append(_observation(
            pid, when, "2339-0", "Glucose [Mass/volume] in Blood",
            readout.glucemia, "mg/dL", "mg/dL"))

    if readout.saturacion_oxigeno is not None:
        observations.append(_observation(
            pid, when, "59408-5", "Oxygen saturation in Arterial blood by Pulse oximetry",
            readout.saturacion_oxigeno, "%", "%"))

    if readout.temperatura is not None:
        observations.append(_observation(
            pid, when, "8310-5", "Body temperature",
            readout.temperatura, "Cel", "Cel"))

    return {
        "resourceType": "Bundle",
        "type": "collection",
        "entry": [{"resource": obs} for obs in observations],
    }

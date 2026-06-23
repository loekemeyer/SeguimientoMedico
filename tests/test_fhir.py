"""Tests del mapeo a FHIR R4 (interoperabilidad HL7)."""
from health_monitor.schemas.clinical import ClinicalReadout
from health_monitor.schemas.fhir import readout_to_fhir_bundle


def test_bundle_presion_arterial_es_panel():
    readout = ClinicalReadout(
        paciente_id=42, presion_sistolica=120, presion_diastolica=80
    )
    bundle = readout_to_fhir_bundle(readout)
    assert bundle["resourceType"] == "Bundle"
    obs = bundle["entry"][0]["resource"]
    assert obs["resourceType"] == "Observation"
    assert obs["code"]["coding"][0]["code"] == "85354-9"  # panel de PA
    assert obs["subject"]["reference"] == "Patient/42"
    componentes = {c["code"]["coding"][0]["code"] for c in obs["component"]}
    assert componentes == {"8480-6", "8462-4"}  # sistólica + diastólica


def test_bundle_incluye_solo_metricas_presentes():
    readout = ClinicalReadout(paciente_id=1, glucemia=110)
    bundle = readout_to_fhir_bundle(readout)
    codes = {
        e["resource"]["code"]["coding"][0]["code"] for e in bundle["entry"]
    }
    assert codes == {"2339-0"}  # solo glucosa


def test_bundle_vacio_sin_metricas():
    readout = ClinicalReadout(paciente_id=1)
    bundle = readout_to_fhir_bundle(readout)
    assert bundle["entry"] == []


def test_bundle_incluye_peso():
    readout = ClinicalReadout(paciente_id=1, peso=80.5)
    bundle = readout_to_fhir_bundle(readout)
    codes = {e["resource"]["code"]["coding"][0]["code"] for e in bundle["entry"]}
    assert "29463-7" in codes  # peso corporal

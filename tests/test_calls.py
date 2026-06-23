"""Tests del motor del scheduler: dispara llamadas, sin doble discado, tolera errores.

Usa una base SQLite en memoria propia y un `caller` falso (sin telefonía real).
"""
from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from health_monitor.calls import disparar_llamadas_pendientes
from health_monitor.db.models import Base, Paciente, Usuario

# 13:00 UTC == 10:00 en Buenos Aires (la hora por defecto del paciente).
_UTC_10_BA = datetime(2026, 6, 22, 13, 0, tzinfo=timezone.utc)  # lunes


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(engine, expire_on_commit=False)()


def _paciente_en_ventana(db) -> Paciente:
    u = Usuario(email="s@t.com", password_hash="x")
    db.add(u)
    db.flush()
    p = Paciente(
        usuario_id=u.id, hce_id="H1", nombre_enc="x", telefono_whatsapp_enc="x",
        consentimiento_firmado=True, llamada_activa=True, activo=True,
        llamada_hora="10:00", llamada_zona="America/Argentina/Buenos_Aires",
        llamada_dias=[],
    )
    db.add(p)
    db.commit()
    return p


def test_dispara_y_marca_la_ultima_llamada():
    db = _session()
    p = _paciente_en_ventana(db)
    llamados: list[int] = []
    regs = disparar_llamadas_pendientes(
        db, _UTC_10_BA, caller=lambda pac: (llamados.append(pac.id) or "SID1")
    )
    assert [r["status"] for r in regs] == ["llamando"]
    assert llamados == [p.id]
    assert p.ultima_llamada_programada is not None


def test_no_dispara_dos_veces_en_la_misma_ventana():
    db = _session()
    _paciente_en_ventana(db)
    disparar_llamadas_pendientes(db, _UTC_10_BA, caller=lambda pac: "SID1")
    # Un tick 4 minutos después (sigue en ventana): NO debe volver a llamar.
    luego = datetime(2026, 6, 22, 13, 4, tzinfo=timezone.utc)
    regs2 = disparar_llamadas_pendientes(db, luego, caller=lambda pac: "SID2")
    assert regs2 == []


def test_error_del_caller_se_registra_y_no_corta():
    db = _session()
    _paciente_en_ventana(db)

    def boom(_pac):
        raise RuntimeError("twilio caído")

    regs = disparar_llamadas_pendientes(db, _UTC_10_BA, caller=boom)
    assert regs[0]["status"] == "error"
    assert "twilio" in regs[0]["detail"]


def test_no_dispara_fuera_de_hora():
    db = _session()
    _paciente_en_ventana(db)
    fuera = datetime(2026, 6, 22, 18, 0, tzinfo=timezone.utc)  # 15:00 BA
    assert disparar_llamadas_pendientes(db, fuera, caller=lambda pac: "SID") == []

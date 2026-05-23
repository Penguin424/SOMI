"""Tests de la Fase 5: buscar_en_vault (integración real con ripgrep)."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from tools.buscar_en_vault import ejecutar as buscar_en_vault, _archivos_por_tipo, _parsear_json_rg
from tools.entrada_diario import ejecutar as entrada_diario
from tools.agregar_pendiente import ejecutar as agregar_pendiente
from tools.log_entrenamiento import ejecutar as log_entrenamiento
from tools.crear_nota import ejecutar as crear_nota


def noop_log(msg: str) -> None:
    pass


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


@pytest.fixture
def vault_poblado(vault: Path) -> Path:
    """Vault con contenido real para buscar."""
    entrada_diario("Hoy terminé el módulo de tools para SOMI", tag="reflexion", vault_path=vault, log_fn=noop_log)
    entrada_diario("Me siento cansado, dormí mal", tag="animo", vault_path=vault, log_fn=noop_log)
    agregar_pendiente("comprar café", prioridad="alta", vault_path=vault, log_fn=noop_log)
    agregar_pendiente("llamar al médico", vault_path=vault, log_fn=noop_log)
    log_entrenamiento(
        [{"nombre": "press banca", "series": 4, "reps": 8, "peso": 80, "unidad": "kg"}],
        vault_path=vault, log_fn=noop_log,
    )
    crear_nota("Notas sobre Raft vs Paxos", "Raft es más simple que Paxos", vault_path=vault, log_fn=noop_log)
    return vault


class TestBuscarEnVault:
    def test_encuentra_texto_existente(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("press banca", vault_path=vault_poblado, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert len(resultado["resultados"]) > 0

    def test_contenido_del_resultado_tiene_el_texto(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("press banca", vault_path=vault_poblado, log_fn=noop_log)
        textos = " ".join(r["contenido"] for r in resultado["resultados"])
        assert "press banca" in textos.lower() or "Press Banca" in textos

    def test_resultado_incluye_ruta_del_archivo(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("press banca", vault_path=vault_poblado, log_fn=noop_log)
        assert all("archivo" in r for r in resultado["resultados"])
        assert all(r["archivo"].endswith(".md") for r in resultado["resultados"])

    def test_ruta_es_relativa_a_la_boveda(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("press banca", vault_path=vault_poblado, log_fn=noop_log)
        for r in resultado["resultados"]:
            assert not r["archivo"].startswith("/"), "La ruta debe ser relativa, no absoluta"

    def test_texto_no_existente_devuelve_lista_vacia(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("xyzzy_no_existe_12345", vault_path=vault_poblado, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert resultado["resultados"] == []

    def test_busqueda_insensible_a_mayusculas(self, vault_poblado: Path) -> None:
        r1 = buscar_en_vault("PRESS BANCA", vault_path=vault_poblado, log_fn=noop_log)
        r2 = buscar_en_vault("press banca", vault_path=vault_poblado, log_fn=noop_log)
        assert len(r1["resultados"]) == len(r2["resultados"])

    def test_filtro_por_tipo_entrenamiento(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("press banca", tipo="entrenamiento", vault_path=vault_poblado, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert len(resultado["resultados"]) > 0
        # Solo deben aparecer archivos de Fitness/Entrenamientos
        for r in resultado["resultados"]:
            assert "Entrenamientos" in r["archivo"] or "Fitness" in r["archivo"]

    def test_filtro_por_tipo_pendiente_encuentra_tareas(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("- [ ]", tipo="pendiente", vault_path=vault_poblado, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert len(resultado["resultados"]) > 0
        contenido = resultado["resultados"][0]["contenido"]
        assert "- [ ]" in contenido

    def test_filtro_por_tipo_sin_archivos_devuelve_mensaje(self, vault: Path) -> None:
        # Vault vacío, buscar tipo que no existe
        resultado = buscar_en_vault("algo", tipo="entrenamiento", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert resultado["resultados"] == []
        assert "mensaje" in resultado

    def test_max_resultados_limita_los_archivos(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("e", max_resultados=2, vault_path=vault_poblado, log_fn=noop_log)
        assert len(resultado["resultados"]) <= 2

    def test_query_vacia_devuelve_error(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("", vault_path=vault_poblado, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_query_solo_espacios_devuelve_error(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("   ", vault_path=vault_poblado, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_busqueda_en_diario(self, vault_poblado: Path) -> None:
        resultado = buscar_en_vault("dormí mal", tipo="diario", vault_path=vault_poblado, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert len(resultado["resultados"]) > 0

    def test_loguea_la_llamada(self, vault_poblado: Path) -> None:
        mensajes: list[str] = []
        buscar_en_vault("press banca", vault_path=vault_poblado, log_fn=lambda m: mensajes.append(m))
        assert any("buscar_en_vault" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)


class TestArchivosPorTipo:
    def test_encuentra_archivos_del_tipo_correcto(self, vault_poblado: Path) -> None:
        archivos = _archivos_por_tipo(vault_poblado, "entrenamiento")
        assert len(archivos) > 0
        assert all(str(a).endswith(".md") for a in archivos)

    def test_tipo_inexistente_devuelve_lista_vacia(self, vault: Path) -> None:
        archivos = _archivos_por_tipo(vault, "tipo_que_no_existe")
        assert archivos == []

    def test_no_confunde_tipos_similares(self, vault_poblado: Path) -> None:
        # "nota" no debe devolver archivos de "nota_general" u otros
        archivos_diario = _archivos_por_tipo(vault_poblado, "diario")
        archivos_entreno = _archivos_por_tipo(vault_poblado, "entrenamiento")
        # No deben solaparse
        rutas_diario = {str(a) for a in archivos_diario}
        rutas_entreno = {str(a) for a in archivos_entreno}
        assert rutas_diario.isdisjoint(rutas_entreno)

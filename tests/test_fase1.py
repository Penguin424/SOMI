"""Tests de la Fase 1: entrada_diario y agregar_pendiente."""
from __future__ import annotations

import sys
from pathlib import Path

# Agrega la raíz del proyecto para poder importar 'tools'
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from datetime import datetime

from tools.entrada_diario import ejecutar as entrada_diario
from tools.agregar_pendiente import ejecutar as agregar_pendiente


def noop_log(msg: str) -> None:
    pass


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


# ---------------------------------------------------------------------------
# entrada_diario
# ---------------------------------------------------------------------------

class TestEntradaDiario:
    def test_crea_archivo_si_no_existe(self, vault: Path) -> None:
        resultado = entrada_diario("Hoy fue un buen día", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        fecha = datetime.now().strftime("%Y-%m-%d")
        assert (vault / "Diario" / f"{fecha}.md").exists()

    def test_frontmatter_contiene_campos_obligatorios(self, vault: Path) -> None:
        entrada_diario("Contenido de prueba", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Diario" / f"{fecha}.md").read_text()
        assert "tipo: diario" in texto
        assert f"fecha: {fecha}" in texto
        assert "tags: []" in texto

    def test_cuerpo_contiene_contenido(self, vault: Path) -> None:
        entrada_diario("Me siento muy bien hoy", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Diario" / f"{fecha}.md").read_text()
        assert "Me siento muy bien hoy" in texto

    def test_cuerpo_contiene_timestamp_hora(self, vault: Path) -> None:
        entrada_diario("Entrada con hora", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        hora = datetime.now().strftime("%H:")  # prefijo de hora es suficiente
        texto = (vault / "Diario" / f"{fecha}.md").read_text()
        assert hora in texto

    def test_tag_se_incluye_en_entrada(self, vault: Path) -> None:
        entrada_diario("Me siento cansado", tag="animo", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Diario" / f"{fecha}.md").read_text()
        assert "#animo" in texto

    def test_sin_tag_no_aparece_hash(self, vault: Path) -> None:
        entrada_diario("Sin tag", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Diario" / f"{fecha}.md").read_text()
        # No debe haber línea de tag
        assert "#reflexion" not in texto
        assert "#animo" not in texto

    def test_segunda_entrada_se_anexa_sin_borrar_la_primera(self, vault: Path) -> None:
        entrada_diario("Primera entrada", vault_path=vault, log_fn=noop_log)
        entrada_diario("Segunda entrada", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Diario" / f"{fecha}.md").read_text()
        assert "Primera entrada" in texto
        assert "Segunda entrada" in texto

    def test_frontmatter_no_se_duplica_en_append(self, vault: Path) -> None:
        entrada_diario("Primera", vault_path=vault, log_fn=noop_log)
        entrada_diario("Segunda", vault_path=vault, log_fn=noop_log)
        fecha = datetime.now().strftime("%Y-%m-%d")
        texto = (vault / "Diario" / f"{fecha}.md").read_text()
        assert texto.count("---") == 2  # solo un bloque frontmatter (apertura y cierre)

    def test_contenido_vacio_devuelve_error(self, vault: Path) -> None:
        resultado = entrada_diario("", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_contenido_solo_espacios_devuelve_error(self, vault: Path) -> None:
        resultado = entrada_diario("   ", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_resultado_contiene_ruta(self, vault: Path) -> None:
        resultado = entrada_diario("Algo", vault_path=vault, log_fn=noop_log)
        assert "path" in resultado
        assert resultado["path"].endswith(".md")

    def test_loguea_la_llamada(self, tmp_path: Path, vault: Path) -> None:
        log_file = tmp_path / "tools.log"
        mensajes: list[str] = []
        entrada_diario("Test log", vault_path=vault, log_fn=lambda m: mensajes.append(m))
        assert any("entrada_diario" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)


# ---------------------------------------------------------------------------
# agregar_pendiente
# ---------------------------------------------------------------------------

class TestAgregarPendiente:
    def test_crea_archivo_si_no_existe(self, vault: Path) -> None:
        resultado = agregar_pendiente("comprar café", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert (vault / "Pendientes.md").exists()

    def test_frontmatter_contiene_tipo_pendiente(self, vault: Path) -> None:
        agregar_pendiente("tarea de prueba", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "tipo: pendiente" in texto

    def test_formato_checkbox(self, vault: Path) -> None:
        agregar_pendiente("comprar café", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "- [ ] comprar café" in texto

    def test_prioridad_alta_tiene_emoji_rojo(self, vault: Path) -> None:
        agregar_pendiente("urgente", prioridad="alta", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "🔴" in texto
        assert "#alta" in texto

    def test_prioridad_media_tiene_emoji_amarillo(self, vault: Path) -> None:
        agregar_pendiente("normal", prioridad="media", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "🟡" in texto

    def test_prioridad_baja_tiene_emoji_verde(self, vault: Path) -> None:
        agregar_pendiente("cuando pueda", prioridad="baja", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "🟢" in texto

    def test_fecha_limite_aparece_con_emoji(self, vault: Path) -> None:
        agregar_pendiente("entregar informe", fecha_limite="2026-05-25", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "📅 2026-05-25" in texto

    def test_contexto_aparece_como_hashtag(self, vault: Path) -> None:
        agregar_pendiente("comprar leche", contexto="compras", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "#compras" in texto

    def test_todos_los_campos_juntos(self, vault: Path) -> None:
        agregar_pendiente(
            "preparar presentación",
            prioridad="alta",
            fecha_limite="2026-05-30",
            contexto="trabajo",
            vault_path=vault,
            log_fn=noop_log,
        )
        texto = (vault / "Pendientes.md").read_text()
        assert "- [ ] preparar presentación" in texto
        assert "🔴" in texto
        assert "📅 2026-05-30" in texto
        assert "#trabajo" in texto

    def test_multiples_tareas_se_anexan(self, vault: Path) -> None:
        agregar_pendiente("tarea uno", vault_path=vault, log_fn=noop_log)
        agregar_pendiente("tarea dos", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Pendientes.md").read_text()
        assert "tarea uno" in texto
        assert "tarea dos" in texto

    def test_tarea_vacia_devuelve_error(self, vault: Path) -> None:
        resultado = agregar_pendiente("", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_resultado_contiene_ruta(self, vault: Path) -> None:
        resultado = agregar_pendiente("algo", vault_path=vault, log_fn=noop_log)
        assert "path" in resultado
        assert resultado["path"].endswith("Pendientes.md")

    def test_loguea_la_llamada(self, vault: Path) -> None:
        mensajes: list[str] = []
        agregar_pendiente("test log", vault_path=vault, log_fn=lambda m: mensajes.append(m))
        assert any("agregar_pendiente" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)

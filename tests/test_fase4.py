"""Tests de la Fase 4: calificar_media y nota_ingles."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from tools.calificar_media import ejecutar as calificar_media
from tools.nota_ingles import ejecutar as nota_ingles


def noop_log(msg: str) -> None:
    pass


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


# ---------------------------------------------------------------------------
# calificar_media
# ---------------------------------------------------------------------------

class TestCalificarMedia:
    def test_crea_archivo_series_si_no_existe(self, vault: Path) -> None:
        resultado = calificar_media("serie", "Severance", 9.0, vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert (vault / "Media" / "Series.md").exists()

    def test_crea_archivo_peliculas_si_no_existe(self, vault: Path) -> None:
        resultado = calificar_media("pelicula", "Dune Parte 2", 8.0, vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert (vault / "Media" / "Peliculas.md").exists()

    def test_serie_tiene_cabecera_correcta(self, vault: Path) -> None:
        calificar_media("serie", "Severance", 9.0, vault_path=vault, log_fn=noop_log)
        texto = (vault / "Media" / "Series.md").read_text()
        assert "Título" in texto
        assert "Temporada" in texto
        assert "Episodio" in texto
        assert "Calificación" in texto

    def test_pelicula_tiene_cabecera_correcta(self, vault: Path) -> None:
        calificar_media("pelicula", "Dune", 8.0, vault_path=vault, log_fn=noop_log)
        texto = (vault / "Media" / "Peliculas.md").read_text()
        assert "Título" in texto
        assert "Calificación" in texto
        assert "Comentario" in texto
        # Películas no tienen columna de temporada/episodio
        assert "Temporada" not in texto

    def test_fila_serie_incluye_todos_los_campos(self, vault: Path) -> None:
        calificar_media(
            "serie", "Severance", 9.0,
            temporada=2, episodio=5,
            comentario="Excelente episodio",
            fecha_visto="2026-05-19",
            vault_path=vault, log_fn=noop_log,
        )
        texto = (vault / "Media" / "Series.md").read_text()
        assert "Severance" in texto
        assert "2" in texto          # temporada
        assert "5" in texto          # episodio
        assert "9.0" in texto
        assert "2026-05-19" in texto
        assert "Excelente episodio" in texto

    def test_fila_pelicula_incluye_todos_los_campos(self, vault: Path) -> None:
        calificar_media(
            "pelicula", "Dune Parte 2", 8.5,
            comentario="Visualmente impresionante",
            fecha_visto="2026-05-18",
            vault_path=vault, log_fn=noop_log,
        )
        texto = (vault / "Media" / "Peliculas.md").read_text()
        assert "Dune Parte 2" in texto
        assert "8.5" in texto
        assert "2026-05-18" in texto
        assert "Visualmente impresionante" in texto

    def test_calificacion_se_formatea_con_un_decimal(self, vault: Path) -> None:
        calificar_media("pelicula", "Test", 9.0, vault_path=vault, log_fn=noop_log)
        texto = (vault / "Media" / "Peliculas.md").read_text()
        assert "9.0" in texto

    def test_multiples_series_se_anexan(self, vault: Path) -> None:
        calificar_media("serie", "Severance", 9.0, vault_path=vault, log_fn=noop_log)
        calificar_media("serie", "The Bear", 8.5, vault_path=vault, log_fn=noop_log)
        texto = (vault / "Media" / "Series.md").read_text()
        assert "Severance" in texto
        assert "The Bear" in texto

    def test_cabecera_no_se_duplica_al_agregar_segunda_entrada(self, vault: Path) -> None:
        calificar_media("serie", "Severance", 9.0, vault_path=vault, log_fn=noop_log)
        calificar_media("serie", "The Bear", 8.5, vault_path=vault, log_fn=noop_log)
        texto = (vault / "Media" / "Series.md").read_text()
        assert texto.count("| Título |") == 1

    def test_series_y_peliculas_van_a_archivos_separados(self, vault: Path) -> None:
        calificar_media("serie", "Severance", 9.0, vault_path=vault, log_fn=noop_log)
        calificar_media("pelicula", "Dune", 8.0, vault_path=vault, log_fn=noop_log)
        assert (vault / "Media" / "Series.md").exists()
        assert (vault / "Media" / "Peliculas.md").exists()
        assert "Dune" not in (vault / "Media" / "Series.md").read_text()
        assert "Severance" not in (vault / "Media" / "Peliculas.md").read_text()

    def test_titulo_vacio_devuelve_error(self, vault: Path) -> None:
        resultado = calificar_media("pelicula", "", 8.0, vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_tipo_invalido_devuelve_error(self, vault: Path) -> None:
        resultado = calificar_media("documental", "Planet Earth", 9.0, vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_calificacion_fuera_de_rango_devuelve_error(self, vault: Path) -> None:
        resultado = calificar_media("pelicula", "Test", 11.0, vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_loguea_la_llamada(self, vault: Path) -> None:
        mensajes: list[str] = []
        calificar_media("serie", "Severance", 9.0, vault_path=vault, log_fn=lambda m: mensajes.append(m))
        assert any("calificar_media" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)


# ---------------------------------------------------------------------------
# nota_ingles
# ---------------------------------------------------------------------------

class TestNotaIngles:
    def test_vocabulario_crea_archivo(self, vault: Path) -> None:
        resultado = nota_ingles("vocabulario", "serendipity", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert (vault / "Ingles" / "Vocabulario.md").exists()

    def test_vocabulario_formato_spaced_repetition(self, vault: Path) -> None:
        nota_ingles(
            "vocabulario", "serendipity",
            traduccion="encontrar algo bueno por casualidad",
            ejemplo="It was pure serendipity",
            vault_path=vault, log_fn=noop_log,
        )
        texto = (vault / "Ingles" / "Vocabulario.md").read_text()
        assert "serendipity :: encontrar algo bueno por casualidad :: It was pure serendipity" in texto

    def test_vocabulario_sin_traduccion_igual_funciona(self, vault: Path) -> None:
        nota_ingles("vocabulario", "serendipity", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Ingles" / "Vocabulario.md").read_text()
        assert "serendipity" in texto

    def test_multiples_palabras_se_anexan(self, vault: Path) -> None:
        nota_ingles("vocabulario", "serendipity", vault_path=vault, log_fn=noop_log)
        nota_ingles("vocabulario", "ephemeral", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Ingles" / "Vocabulario.md").read_text()
        assert "serendipity" in texto
        assert "ephemeral" in texto

    def test_expresion_va_al_mismo_archivo_con_prefijo(self, vault: Path) -> None:
        nota_ingles(
            "expresion", "to get the hang of it",
            traduccion="cogerle el truco",
            vault_path=vault, log_fn=noop_log,
        )
        texto = (vault / "Ingles" / "Vocabulario.md").read_text()
        assert "[expr]" in texto
        assert "to get the hang of it" in texto
        assert "cogerle el truco" in texto

    def test_gramatica_crea_archivo_separado(self, vault: Path) -> None:
        resultado = nota_ingles("gramatica", "Present Perfect vs Simple Past", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert (vault / "Ingles" / "Gramatica.md").exists()

    def test_gramatica_formato_seccion_h2(self, vault: Path) -> None:
        nota_ingles(
            "gramatica", "Present Perfect vs Simple Past",
            ejemplo="I have been to Paris vs I went to Paris",
            vault_path=vault, log_fn=noop_log,
        )
        texto = (vault / "Ingles" / "Gramatica.md").read_text()
        assert "## Present Perfect vs Simple Past" in texto
        assert "I have been to Paris" in texto

    def test_multiples_temas_de_gramatica_se_anexan(self, vault: Path) -> None:
        nota_ingles("gramatica", "Present Perfect", vault_path=vault, log_fn=noop_log)
        nota_ingles("gramatica", "Conditional Type 2", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Ingles" / "Gramatica.md").read_text()
        assert "## Present Perfect" in texto
        assert "## Conditional Type 2" in texto

    def test_nota_general_crea_archivo_en_notas(self, vault: Path) -> None:
        resultado = nota_ingles("nota_general", "Notas sobre el acento americano", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert (vault / "Ingles" / "Notas").is_dir()
        archivos = list((vault / "Ingles" / "Notas").glob("*.md"))
        assert len(archivos) == 1

    def test_nota_general_contiene_el_contenido(self, vault: Path) -> None:
        nota_ingles("nota_general", "El acento rioplatense es muy musical", vault_path=vault, log_fn=noop_log)
        archivos = list((vault / "Ingles" / "Notas").glob("*.md"))
        texto = archivos[0].read_text()
        assert "El acento rioplatense" in texto

    def test_contenido_vacio_devuelve_error(self, vault: Path) -> None:
        resultado = nota_ingles("vocabulario", "", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_categoria_invalida_devuelve_error(self, vault: Path) -> None:
        resultado = nota_ingles("pronunciacion", "test", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_loguea_la_llamada(self, vault: Path) -> None:
        mensajes: list[str] = []
        nota_ingles("vocabulario", "test", vault_path=vault, log_fn=lambda m: mensajes.append(m))
        assert any("nota_ingles" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)

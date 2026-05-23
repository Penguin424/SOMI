"""Tests de la Fase 2: guardar_snippet y crear_nota."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from tools.guardar_snippet import ejecutar as guardar_snippet
from tools.crear_nota import ejecutar as crear_nota


def noop_log(msg: str) -> None:
    pass


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    v = tmp_path / "vault"
    v.mkdir()
    return v


# ---------------------------------------------------------------------------
# guardar_snippet
# ---------------------------------------------------------------------------

class TestGuardarSnippet:
    def test_crea_archivo_en_categoria_git(self, vault: Path) -> None:
        resultado = guardar_snippet(
            categoria="git",
            titulo="Log visual",
            contenido="git log --oneline --graph",
            vault_path=vault,
            log_fn=noop_log,
        )
        assert resultado["status"] == "ok"
        assert (vault / "Snippets" / "Git.md").exists()

    def test_cada_categoria_va_a_su_archivo(self, vault: Path) -> None:
        mapeo = {
            "linux": "Linux.md",
            "proton": "Proton.md",
            "git": "Git.md",
            "hyprland": "Hyprland.md",
            "otro": "Otros.md",
        }
        for cat, archivo in mapeo.items():
            guardar_snippet(
                categoria=cat,
                titulo=f"Test {cat}",
                contenido="comando de prueba",
                vault_path=vault,
                log_fn=noop_log,
            )
            assert (vault / "Snippets" / archivo).exists(), f"No creó {archivo} para categoría {cat}"

    def test_frontmatter_contiene_tipo_snippet(self, vault: Path) -> None:
        guardar_snippet("linux", "test", "ls -la", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Snippets" / "Linux.md").read_text()
        assert "tipo: snippet" in texto

    def test_seccion_tiene_titulo_como_h2(self, vault: Path) -> None:
        guardar_snippet("git", "Mi comando", "git status", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Snippets" / "Git.md").read_text()
        assert "## Mi comando" in texto

    def test_contenido_en_bloque_de_codigo(self, vault: Path) -> None:
        guardar_snippet("linux", "Listar procesos", "ps aux | grep python", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Snippets" / "Linux.md").read_text()
        assert "```bash" in texto
        assert "ps aux | grep python" in texto
        assert "```" in texto

    def test_descripcion_aparece_antes_del_codigo(self, vault: Path) -> None:
        guardar_snippet(
            "git",
            "Stash todo",
            "git stash --include-untracked",
            descripcion="Guarda cambios temporalmente incluyendo archivos nuevos",
            vault_path=vault,
            log_fn=noop_log,
        )
        texto = (vault / "Snippets" / "Git.md").read_text()
        assert "Guarda cambios temporalmente" in texto
        # La descripción debe aparecer antes del bloque de código
        pos_desc = texto.index("Guarda cambios")
        pos_code = texto.index("```bash")
        assert pos_desc < pos_code

    def test_tags_aparecen_con_hashtag(self, vault: Path) -> None:
        guardar_snippet(
            "linux",
            "Permisos",
            "chmod +x script.sh",
            tags=["permisos", "archivos"],
            vault_path=vault,
            log_fn=noop_log,
        )
        texto = (vault / "Snippets" / "Linux.md").read_text()
        assert "#permisos" in texto
        assert "#archivos" in texto

    def test_multiples_snippets_se_anexan(self, vault: Path) -> None:
        guardar_snippet("git", "Snippet A", "git add .", vault_path=vault, log_fn=noop_log)
        guardar_snippet("git", "Snippet B", "git commit -m 'msg'", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Snippets" / "Git.md").read_text()
        assert "Snippet A" in texto
        assert "Snippet B" in texto

    def test_frontmatter_no_se_duplica(self, vault: Path) -> None:
        guardar_snippet("git", "A", "cmd1", vault_path=vault, log_fn=noop_log)
        guardar_snippet("git", "B", "cmd2", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Snippets" / "Git.md").read_text()
        assert texto.count("---") == 2

    def test_titulo_vacio_devuelve_error(self, vault: Path) -> None:
        resultado = guardar_snippet("git", "", "git status", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_contenido_vacio_devuelve_error(self, vault: Path) -> None:
        resultado = guardar_snippet("git", "Titulo", "", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_categoria_invalida_devuelve_error(self, vault: Path) -> None:
        resultado = guardar_snippet("javascript", "Test", "const x = 1", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_resultado_contiene_ruta(self, vault: Path) -> None:
        resultado = guardar_snippet("linux", "test", "echo hola", vault_path=vault, log_fn=noop_log)
        assert "path" in resultado
        assert "Linux.md" in resultado["path"]

    def test_loguea_la_llamada(self, vault: Path) -> None:
        mensajes: list[str] = []
        guardar_snippet("git", "log test", "git log", vault_path=vault, log_fn=lambda m: mensajes.append(m))
        assert any("guardar_snippet" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)


# ---------------------------------------------------------------------------
# crear_nota
# ---------------------------------------------------------------------------

class TestCrearNota:
    def test_crea_archivo_en_inbox_por_defecto(self, vault: Path) -> None:
        resultado = crear_nota("Mi primera nota", "Contenido de prueba", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "ok"
        assert (vault / "Inbox").is_dir()

    def test_nombre_de_archivo_es_slug_del_titulo(self, vault: Path) -> None:
        crear_nota("Reunión del equipo", "Notas de la reunión", vault_path=vault, log_fn=noop_log)
        assert (vault / "Inbox" / "reunion-del-equipo.md").exists()

    def test_slug_elimina_acentos(self, vault: Path) -> None:
        crear_nota("Análisis técnico", "Contenido", vault_path=vault, log_fn=noop_log)
        assert (vault / "Inbox" / "analisis-tecnico.md").exists()

    def test_frontmatter_contiene_campos_obligatorios(self, vault: Path) -> None:
        crear_nota("Nota test", "Contenido test", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Inbox" / "nota-test.md").read_text()
        assert "tipo: nota" in texto
        assert "titulo: Nota test" in texto

    def test_cuerpo_contiene_titulo_como_h1(self, vault: Path) -> None:
        crear_nota("Mi nota", "El contenido aquí", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Inbox" / "mi-nota.md").read_text()
        assert "# Mi nota" in texto

    def test_cuerpo_contiene_el_contenido(self, vault: Path) -> None:
        crear_nota("Test", "Este es el contenido importante", vault_path=vault, log_fn=noop_log)
        texto = (vault / "Inbox" / "test.md").read_text()
        assert "Este es el contenido importante" in texto

    def test_tags_en_frontmatter(self, vault: Path) -> None:
        crear_nota("Nota con tags", "Contenido", tags=["ideas", "proyecto"], vault_path=vault, log_fn=noop_log)
        texto = (vault / "Inbox" / "nota-con-tags.md").read_text()
        assert "ideas" in texto
        assert "proyecto" in texto

    def test_carpeta_personalizada(self, vault: Path) -> None:
        crear_nota("Nota en otra carpeta", "Contenido", carpeta="Ingles/Notas", vault_path=vault, log_fn=noop_log)
        assert (vault / "Ingles" / "Notas" / "nota-en-otra-carpeta.md").exists()

    def test_archivo_existente_genera_sufijo_timestamp(self, vault: Path) -> None:
        crear_nota("Duplicada", "Primera versión", vault_path=vault, log_fn=noop_log)
        crear_nota("Duplicada", "Segunda versión", vault_path=vault, log_fn=noop_log)
        archivos = list((vault / "Inbox").glob("duplicada*.md"))
        assert len(archivos) == 2

    def test_segunda_nota_no_sobreescribe_la_primera(self, vault: Path) -> None:
        crear_nota("Duplicada", "Primera versión", vault_path=vault, log_fn=noop_log)
        crear_nota("Duplicada", "Segunda versión", vault_path=vault, log_fn=noop_log)
        contenidos = [(vault / "Inbox" / f).read_text() for f in
                      [a.name for a in (vault / "Inbox").glob("duplicada*.md")]]
        textos = " ".join(contenidos)
        assert "Primera versión" in textos
        assert "Segunda versión" in textos

    def test_titulo_vacio_devuelve_error(self, vault: Path) -> None:
        resultado = crear_nota("", "Contenido", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_contenido_vacio_devuelve_error(self, vault: Path) -> None:
        resultado = crear_nota("Titulo", "", vault_path=vault, log_fn=noop_log)
        assert resultado["status"] == "error"

    def test_resultado_contiene_ruta(self, vault: Path) -> None:
        resultado = crear_nota("Test ruta", "contenido", vault_path=vault, log_fn=noop_log)
        assert "path" in resultado
        assert resultado["path"].endswith(".md")

    def test_loguea_la_llamada(self, vault: Path) -> None:
        mensajes: list[str] = []
        crear_nota("Log test", "contenido", vault_path=vault, log_fn=lambda m: mensajes.append(m))
        assert any("crear_nota" in m for m in mensajes)
        assert any("status=ok" in m for m in mensajes)

#!/usr/bin/env python3
"""SOMI overlay — HUD flotante estilo Cyberpunk 2077 durante reproducción de TTS.

Se lanza como proceso independiente desde pipeline.py justo antes de paplay
y se termina con SIGTERM cuando el audio termina.
"""
from __future__ import annotations

import math
import random
import signal
import sys

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gtk4LayerShell", "1.0")
from gi.repository import Gio, GLib, Gtk, Gtk4LayerShell

# ---------------------------------------------------------------------------
# Paleta Cyberpunk 2077
# ---------------------------------------------------------------------------
_Y  = (1.000, 0.882, 0.000)   # #FFE100 — amarillo Cyberpunk
_C  = (0.000, 0.882, 1.000)   # #00E1FF — cyan neón
_G  = (0.100, 1.000, 0.300)   # #1AFF4D — verde status
_BG = (0.035, 0.035, 0.035)   # #090909 — casi negro

_W, _H = 360, 170

# ---------------------------------------------------------------------------
# Estado de la animación (módulo-level para acceso desde callbacks)
# ---------------------------------------------------------------------------
_N_BARS = 20
_bars   = [random.uniform(0.2, 0.8) for _ in range(_N_BARS)]
_target = [random.uniform(0.1, 1.0) for _ in range(_N_BARS)]
_tick   = 0


def _draw(area: Gtk.DrawingArea, cr, w: int, h: int, _data) -> None:
    global _tick
    _tick += 1

    # ── Fondo ──────────────────────────────────────────────────────────────
    cr.set_source_rgb(*_BG)
    cr.paint()

    # ── Borde principal (2px amarillo) ─────────────────────────────────────
    cr.set_source_rgb(*_Y)
    cr.set_line_width(2.0)
    cr.rectangle(1, 1, w - 2, h - 2)
    cr.stroke()

    # ── Líneas de acento (esquina superior izquierda) ───────────────────────
    cr.set_line_width(1.0)
    cr.move_to(8, 6);  cr.line_to(w // 2 - 10, 6); cr.stroke()
    cr.move_to(8, 6);  cr.line_to(8, 14);           cr.stroke()

    # ── Bracket esquina superior derecha ───────────────────────────────────
    cr.move_to(w - 8, 6);  cr.line_to(w - 36, 6);  cr.stroke()
    cr.move_to(w - 8, 6);  cr.line_to(w - 8, 22);  cr.stroke()

    # ── Callsign "◈ SONGBIRD" ──────────────────────────────────────────────
    cr.set_source_rgb(*_Y)
    cr.select_font_face("monospace", 0, 1)
    cr.set_font_size(14)
    cr.move_to(14, 28)
    cr.show_text("◈  SONGBIRD")

    # ── Indicador LIVE (dot pulsante) ──────────────────────────────────────
    pulse = 0.65 + 0.35 * math.sin(_tick * 0.15)
    cr.set_source_rgba(*_G, pulse)
    cr.arc(w - 26, 21, 5, 0, 2 * math.pi)
    cr.fill()
    cr.set_source_rgba(*_G, 0.9)
    cr.select_font_face("monospace", 0, 0)
    cr.set_font_size(8)
    cr.move_to(w - 58, 24)
    cr.show_text("● LIVE")

    # ── Línea de estado (TX ACTIVO...) ─────────────────────────────────────
    cr.set_source_rgb(*_C)
    cr.set_font_size(9)
    dots = "." * ((_tick // 9) % 4)
    cr.move_to(14, 46)
    cr.show_text(f"TX ACTIVO{dots:<3}   //   NET RUNNER ELITE")

    # ── Separador ──────────────────────────────────────────────────────────
    cr.set_source_rgba(*_Y, 0.22)
    cr.set_line_width(0.5)
    cr.move_to(8, 54); cr.line_to(w - 8, 54); cr.stroke()

    # ── Ecualizador animado ─────────────────────────────────────────────────
    zone_top = 62
    zone_h   = h - zone_top - 20
    slot_w   = (w - 20) / _N_BARS

    for i in range(_N_BARS):
        _bars[i] += (_target[i] - _bars[i]) * 0.18
        if random.random() < 0.07:
            _target[i] = random.uniform(0.05, 1.0)

        bh = max(3.0, _bars[i] * zone_h)
        bx = 10 + i * slot_w + 1
        by = zone_top + zone_h - bh
        bw = max(1.0, slot_w - 2)

        # Degradado amarillo → cyan según altura
        t = _bars[i]
        r = _Y[0] + (_C[0] - _Y[0]) * t
        g = _Y[1] + (_C[1] - _Y[1]) * t
        b = _Y[2] + (_C[2] - _Y[2]) * t
        cr.set_source_rgb(r, g, b)
        cr.rectangle(bx, by, bw, bh)
        cr.fill()

        # Tope brillante
        cr.set_source_rgba(1, 1, 1, 0.55)
        cr.rectangle(bx, by, bw, 2)
        cr.fill()

    # ── Línea de glitch ocasional ───────────────────────────────────────────
    if random.random() < 0.035:
        gy  = random.randint(56, h - 22)
        gx0 = random.randint(0, w // 2)
        gx1 = gx0 + random.randint(30, 140)
        cr.set_source_rgba(*_C, random.uniform(0.3, 0.65))
        cr.set_line_width(1)
        cr.move_to(gx0, gy); cr.line_to(gx1, gy); cr.stroke()

    # ── Footer ─────────────────────────────────────────────────────────────
    cr.set_source_rgba(1, 1, 1, 0.28)
    cr.select_font_face("monospace", 0, 0)
    cr.set_font_size(7.5)
    cr.move_to(14, h - 7)
    cr.show_text("NIGHT CITY  2077  //  PHANTOM LIBERTY PROTOCOL")

    # Línea de acento inferior derecha
    cr.set_source_rgba(*_Y, 0.4)
    cr.set_line_width(1)
    cr.move_to(w - 8, h - 6); cr.line_to(w - 36, h - 6); cr.stroke()
    cr.move_to(w - 8, h - 6); cr.line_to(w - 8, h - 18); cr.stroke()


def _on_tick(area: Gtk.DrawingArea) -> bool:
    area.queue_draw()
    return GLib.SOURCE_CONTINUE


class OverlayApp(Gtk.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="com.somi.overlay",
            flags=Gio.ApplicationFlags.NON_UNIQUE,
        )

    def do_activate(self) -> None:
        win = Gtk.ApplicationWindow(application=self)
        win.set_title("SOMI")
        win.set_decorated(False)

        # ── Layer shell: anclar esquina superior derecha ────────────────────
        Gtk4LayerShell.init_for_window(win)
        Gtk4LayerShell.set_layer(win, Gtk4LayerShell.Layer.TOP)
        Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.TOP, True)
        Gtk4LayerShell.set_anchor(win, Gtk4LayerShell.Edge.RIGHT, True)
        Gtk4LayerShell.set_margin(win, Gtk4LayerShell.Edge.TOP, 20)
        Gtk4LayerShell.set_margin(win, Gtk4LayerShell.Edge.RIGHT, 20)
        Gtk4LayerShell.set_namespace(win, "somi-overlay")
        Gtk4LayerShell.set_keyboard_mode(win, Gtk4LayerShell.KeyboardMode.NONE)

        # ── DrawingArea ─────────────────────────────────────────────────────
        area = Gtk.DrawingArea()
        area.set_content_width(_W)
        area.set_content_height(_H)
        area.set_draw_func(_draw, None)

        GLib.timeout_add(50, _on_tick, area)   # 20 FPS

        win.set_child(area)
        win.present()

        # ── SIGTERM → salida limpia ──────────────────────────────────────────
        signal.signal(signal.SIGTERM, lambda *_: self.quit())
        signal.signal(signal.SIGINT,  lambda *_: self.quit())


if __name__ == "__main__":
    app = OverlayApp()
    sys.exit(app.run([]))

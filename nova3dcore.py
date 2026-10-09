from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor
from PySide6.QtOpenGLWidgets import QOpenGLWidget
from PySide6.QtWidgets import QApplication, QMainWindow

from OpenGL.GL import (
    GL_BLEND,
    GL_COLOR_BUFFER_BIT,
    GL_DEPTH_BUFFER_BIT,
    GL_DEPTH_TEST,
    GL_LINE_LOOP,
    GL_LINES,
    GL_ONE,
    GL_ONE_MINUS_SRC_ALPHA,
    GL_POINTS,
    GL_SRC_ALPHA,
    GL_SMOOTH,
    GL_TRIANGLE_FAN,
    GL_LINE_STRIP,
    glBegin,
    glBlendFunc,
    glClear,
    glClearColor,
    glColor4f,
    glDepthFunc,
    glDisable,
    glEnable,
    glEnd,
    glLineWidth,
    glLoadIdentity,
    glMatrixMode,
    glPointSize,
    glPopMatrix,
    glPushMatrix,
    glRotatef,
    glShadeModel,
    glTranslatef,
    glVertex3f,
    glViewport,
)

from OpenGL.GL import GL_MODELVIEW, GL_PROJECTION, GL_LEQUAL


# ============================================================
# CONFIG
# ============================================================

BACKGROUND = (0.008, 0.015, 0.021)

CYAN = (0.18, 0.88, 1.00)
GREEN = (0.18, 1.00, 0.68)
PURPLE = (0.62, 0.35, 1.00)
WHITE = (0.72, 0.92, 1.00)
DIM = (0.18, 0.35, 0.42)


# ============================================================
# PARTICLES
# ============================================================

@dataclass
class Particle:
    angle: float
    radius: float
    height: float
    speed: float
    size: float
    phase: float


@dataclass
class NeuralNode:
    x: float
    y: float
    z: float
    phase: float


# ============================================================
# NOVA 3D CORE
# ============================================================

class Nova3DCore(QOpenGLWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAutoFillBackground(False)
        self.setMinimumSize(500, 500)

        # ----------------------------------------------------
        # STATE
        # ----------------------------------------------------

        self.state = "idle"

        self.rotation = 0.0
        self.inner_rotation = 0.0
        self.energy = 0.20
        self.target_energy = 0.20

        self.time = 0.0

        # ----------------------------------------------------
        # RANDOM GENERATOR
        # ----------------------------------------------------

        self.rng = random.Random(42)

        # ----------------------------------------------------
        # PARTICLES
        # ----------------------------------------------------

        self.particles: list[Particle] = []

        for _ in range(170):

            self.particles.append(
                Particle(
                    angle=self.rng.uniform(0, math.tau),
                    radius=self.rng.uniform(1.25, 2.25),
                    height=self.rng.uniform(-0.85, 0.85),
                    speed=self.rng.uniform(0.15, 0.55),
                    size=self.rng.uniform(1.2, 3.5),
                    phase=self.rng.uniform(0, math.tau),
                )
            )

        # ----------------------------------------------------
        # NEURAL NODES
        # ----------------------------------------------------

        self.nodes: list[NeuralNode] = []

        for _ in range(65):

            while True:

                x = self.rng.uniform(-1.0, 1.0)
                y = self.rng.uniform(-1.0, 1.0)
                z = self.rng.uniform(-1.0, 1.0)

                distance = math.sqrt(
                    x * x +
                    y * y +
                    z * z
                )

                if distance <= 1.0:
                    break

            scale = 0.88 / max(distance, 0.001)

            self.nodes.append(
                NeuralNode(
                    x * scale,
                    y * scale,
                    z * scale,
                    self.rng.uniform(0, math.tau),
                )
            )

        # ----------------------------------------------------
        # TIMER
        # ----------------------------------------------------

        self.timer = QTimer(self)

        self.timer.timeout.connect(self.animate)

        self.timer.start(16)

    # ========================================================
    # STATE
    # ========================================================

    def set_state(self, state: str):

        state = (state or "idle").lower().strip()

        valid_states = {
            "idle",
            "active",
            "listening",
            "thinking",
            "speaking",
            "stopping",
        }

        if state not in valid_states:
            state = "idle"

        self.state = state

        self.target_energy = {
            "idle": 0.22,
            "active": 0.65,
            "listening": 1.00,
            "thinking": 1.30,
            "speaking": 1.10,
            "stopping": 0.05,
        }[state]

        self.update()

    # ========================================================
    # COLORS
    # ========================================================

    def state_color(self):

        if self.state == "thinking":
            return PURPLE

        if self.state in (
            "active",
            "listening",
        ):
            return GREEN

        if self.state == "speaking":
            return CYAN

        if self.state == "stopping":
            return DIM

        return CYAN

    # ========================================================
    # ANIMATION
    # ========================================================

    def animate(self):

        self.time += 0.016

        self.energy += (
            self.target_energy -
            self.energy
        ) * 0.055

        speed = {
            "idle": 0.25,
            "active": 0.70,
            "listening": 1.20,
            "thinking": 2.00,
            "speaking": 1.45,
            "stopping": 0.12,
        }.get(
            self.state,
            0.25,
        )

        self.rotation += 0.35 * speed

        self.inner_rotation -= 0.55 * speed

        for particle in self.particles:

            particle.angle += (
                particle.speed *
                0.01 *
                speed
            )

        self.update()

    # ========================================================
    # OPENGL INITIALIZATION
    # ========================================================

    def initializeGL(self):

        glClearColor(
    0.0,
    0.0,
    0.0,
    0.0,
)

        glEnable(GL_DEPTH_TEST)

        glDepthFunc(GL_LEQUAL)

        glEnable(GL_BLEND)

        glBlendFunc(
            GL_SRC_ALPHA,
            GL_ONE_MINUS_SRC_ALPHA,
        )

        glShadeModel(GL_SMOOTH)

    # ========================================================
    # RESIZE
    # ========================================================

    def resizeGL(self, width, height):

        height = max(height, 1)

        glViewport(
            0,
            0,
            width,
            height,
        )

        glMatrixMode(GL_PROJECTION)

        glLoadIdentity()

        aspect = width / float(height)

        self.perspective(
            45.0,
            aspect,
            0.1,
            100.0,
        )

        glMatrixMode(GL_MODELVIEW)

    # ========================================================
    # PERSPECTIVE
    # ========================================================

    def perspective(
        self,
        fov,
        aspect,
        near,
        far,
    ):

        # Manual perspective matrix.
        #
        # This avoids depending on GLU.

        f = 1.0 / math.tan(
            math.radians(fov) / 2.0
        )

        matrix = [
            f / aspect, 0, 0, 0,
            0, f, 0, 0,
            0, 0,
            (far + near) / (near - far),
            -1,
            0, 0,
            (2 * far * near) / (near - far),
            0,
        ]

        # PyOpenGL accepts the list
        # in column-major order.

        from OpenGL.GL import glLoadMatrixf

        glLoadMatrixf(matrix)

    # ========================================================
    # DRAW
    # ========================================================

    def paintGL(self):

        glClear(
            GL_COLOR_BUFFER_BIT |
            GL_DEPTH_BUFFER_BIT
        )

        glMatrixMode(GL_MODELVIEW)

        glLoadIdentity()

        # Camera distance.
        glTranslatef(
            0.0,
            0.0,
            -6.7,
        )

        # ----------------------------------------------------
        # CENTRAL ROTATION
        # ----------------------------------------------------

        glPushMatrix()

        glRotatef(
            self.rotation,
            0.0,
            1.0,
            0.0,
        )

        # ----------------------------------------------------
        # ENERGY FIELD
        # ----------------------------------------------------

        self.draw_energy_field()

        # ----------------------------------------------------
        # NEURAL NETWORK
        # ----------------------------------------------------

        self.draw_neural_network()

        # ----------------------------------------------------
        # ORBITAL RINGS
        # ----------------------------------------------------

        self.draw_orbits()

        glPopMatrix()

        # ----------------------------------------------------
        # PARTICLES
        # ----------------------------------------------------

        self.draw_particles()

        # ----------------------------------------------------
        # CORE
        # ----------------------------------------------------

        self.draw_core()

        # ----------------------------------------------------
        # OUTER GLOW
        # ----------------------------------------------------

        self.draw_glow()

    # ========================================================
    # ENERGY FIELD
    # ========================================================

    def draw_energy_field(self):

        color = self.state_color()

        glDisable(GL_DEPTH_TEST)

        for layer in range(7):

            radius = (
                0.70 +
                layer * 0.085 +
                math.sin(
                    self.time * 2.0 +
                    layer
                ) * 0.025
            )

            alpha = (
                0.030 *
                self.energy *
                (7 - layer)
            )

            glColor4f(
                color[0],
                color[1],
                color[2],
                alpha,
            )

            glBegin(GL_TRIANGLE_FAN)

            glVertex3f(
                0,
                0,
                0,
            )

            for i in range(33):

                angle = (
                    math.tau *
                    i /
                    32
                )

                x = math.cos(angle) * radius

                y = math.sin(angle) * radius

                glVertex3f(
                    x,
                    y,
                    0,
                )

            glEnd()

        glEnable(GL_DEPTH_TEST)

    # ========================================================
    # CORE SPHERE
    # ========================================================

    def draw_core(self):

        color = self.state_color()

        pulse = (
            math.sin(
                self.time *
                (
                    2.0 +
                    self.energy * 4.0
                )
            )
            + 1.0
        ) / 2.0

        radius = (
            0.82 +
            pulse *
            0.035 *
            self.energy
        )

        # ----------------------------------------------------
        # INNER SPHERE
        # ----------------------------------------------------

        glPushMatrix()

        glRotatef(
            self.inner_rotation,
            1.0,
            0.4,
            0.2,
        )

        self.draw_wire_sphere(
            radius,
            color,
            0.20 +
            self.energy * 0.18,
        )

        glPopMatrix()

        # ----------------------------------------------------
        # INNER ENERGY ORB
        # ----------------------------------------------------

        glDisable(GL_DEPTH_TEST)

        glBlendFunc(
            GL_SRC_ALPHA,
            GL_ONE,
        )

        for layer in range(5):

            r = (
                0.32 +
                layer * 0.11
            )

            alpha = (
                0.045 *
                self.energy *
                (5 - layer)
            )

            glColor4f(
                color[0],
                color[1],
                color[2],
                alpha,
            )

            self.draw_flat_circle(r)

        glBlendFunc(
            GL_SRC_ALPHA,
            GL_ONE_MINUS_SRC_ALPHA,
        )

        glEnable(GL_DEPTH_TEST)

    # ========================================================
    # WIRE SPHERE
    # ========================================================

    def draw_wire_sphere(
        self,
        radius,
        color,
        alpha,
    ):

        glLineWidth(1.0)

        glColor4f(
            color[0],
            color[1],
            color[2],
            alpha,
        )

        # Longitude lines.

        for longitude in range(
            0,
            360,
            20,
        ):

            angle = math.radians(
                longitude
            )

            glBegin(GL_LINE_STRIP)

            for latitude in range(
                -90,
                91,
                6,
            ):

                lat = math.radians(
                    latitude
                )

                x = (
                    radius *
                    math.cos(lat) *
                    math.cos(angle)
                )

                y = (
                    radius *
                    math.sin(lat)
                )

                z = (
                    radius *
                    math.cos(lat) *
                    math.sin(angle)
                )

                glVertex3f(
                    x,
                    y,
                    z,
                )

            glEnd()

        # Latitude lines.

        for latitude in range(
            -60,
            61,
            20,
        ):

            lat = math.radians(
                latitude
            )

            glBegin(GL_LINE_LOOP)

            for longitude in range(
                0,
                360,
                6,
            ):

                lon = math.radians(
                    longitude
                )

                x = (
                    radius *
                    math.cos(lat) *
                    math.cos(lon)
                )

                y = (
                    radius *
                    math.sin(lat)
                )

                z = (
                    radius *
                    math.cos(lat) *
                    math.sin(lon)
                )

                glVertex3f(
                    x,
                    y,
                    z,
                )

            glEnd()

    # ========================================================
    # NEURAL NETWORK
    # ========================================================

    def draw_neural_network(self):

        color = self.state_color()

        # ----------------------------------------------------
        # CONNECTIONS
        # ----------------------------------------------------

        glLineWidth(1.0)

        for i, node_a in enumerate(
            self.nodes
        ):

            connections = 0

            for j in range(
                i + 1,
                len(self.nodes),
            ):

                node_b = self.nodes[j]

                dx = (
                    node_a.x -
                    node_b.x
                )

                dy = (
                    node_a.y -
                    node_b.y
                )

                dz = (
                    node_a.z -
                    node_b.z
                )

                distance = math.sqrt(
                    dx * dx +
                    dy * dy +
                    dz * dz
                )

                if distance < 0.42:

                    alpha = (
                        0.04 +
                        self.energy *
                        0.10
                    )

                    glColor4f(
                        color[0],
                        color[1],
                        color[2],
                        alpha,
                    )

                    glBegin(GL_LINES)

                    glVertex3f(
                        node_a.x,
                        node_a.y,
                        node_a.z,
                    )

                    glVertex3f(
                        node_b.x,
                        node_b.y,
                        node_b.z,
                    )

                    glEnd()

                    connections += 1

                    if connections >= 3:
                        break

        # ----------------------------------------------------
        # NODES
        # ----------------------------------------------------

        glPointSize(3.0)

        glColor4f(
            color[0],
            color[1],
            color[2],
            0.65 +
            self.energy * 0.25,
        )

        glBegin(GL_POINTS)

        for node in self.nodes:

            pulse = (
                math.sin(
                    self.time * 3.0 +
                    node.phase
                )
                + 1.0
            ) / 2.0

            scale = (
                1.0 +
                pulse *
                0.035 *
                self.energy
            )

            glVertex3f(
                node.x * scale,
                node.y * scale,
                node.z * scale,
            )

        glEnd()

    # ========================================================
    # ORBITAL RINGS
    # ========================================================

    def draw_orbits(self):

        color = self.state_color()

        ring_data = [
            (1.20, 0.0, 0.0, 0.0),
            (1.43, 58.0, 0.0, 24.0),
            (1.67, -47.0, 24.0, 0.0),
            (1.91, 72.0, 15.0, 48.0),
        ]

        for index, (
            radius,
            tilt_x,
            tilt_y,
            tilt_z,
        ) in enumerate(ring_data):

            glPushMatrix()

            glRotatef(
                tilt_x +
                self.rotation *
                (0.25 + index * 0.08),
                1,
                0,
                0,
            )

            glRotatef(
                tilt_y +
                self.rotation *
                (0.15 + index * 0.05),
                0,
                1,
                0,
            )

            glRotatef(
                tilt_z,
                0,
                0,
                1,
            )

            alpha = (
                0.18 +
                self.energy *
                0.15
            )

            glColor4f(
                color[0],
                color[1],
                color[2],
                alpha,
            )

            glLineWidth(
                1.0 if index else 1.5
            )

            glBegin(GL_LINE_LOOP)

            for point in range(
                128
            ):

                angle = (
                    math.tau *
                    point /
                    128
                )

                x = (
                    math.cos(angle) *
                    radius
                )

                z = (
                    math.sin(angle) *
                    radius
                )

                glVertex3f(
                    x,
                    0,
                    z,
                )

            glEnd()

            # Energy nodes travelling
            # around the orbit.

            marker_angle = (
                self.time *
                (
                    0.35 +
                    index * 0.18
                )
            )

            mx = (
                math.cos(
                    marker_angle
                ) *
                radius
            )

            mz = (
                math.sin(
                    marker_angle
                ) *
                radius
            )

            glPointSize(
                5.0 +
                self.energy * 3.0
            )

            glColor4f(
                0.75,
                0.96,
                1.0,
                0.85,
            )

            glBegin(GL_POINTS)

            glVertex3f(
                mx,
                0,
                mz,
            )

            glEnd()

            glPopMatrix()

    # ========================================================
    # PARTICLES
    # ========================================================

    def draw_particles(self):

        color = self.state_color()

        glDisable(GL_DEPTH_TEST)

        glPointSize(2.0)

        glBegin(GL_POINTS)

        for particle in self.particles:

            angle = particle.angle

            radius = particle.radius

            wobble = math.sin(
                self.time *
                particle.speed *
                4.0 +
                particle.phase
            ) * 0.10

            x = math.cos(angle) * (
                radius + wobble
            )

            z = math.sin(angle) * (
                radius + wobble
            )

            y = (
                particle.height
                +
                math.sin(
                    self.time *
                    0.8 +
                    particle.phase
                ) * 0.10
            )

            brightness = (
                0.25 +
                self.energy * 0.65
            )

            glColor4f(
                color[0],
                color[1],
                color[2],
                brightness,
            )

            glVertex3f(
                x,
                y,
                z,
            )

        glEnd()

        glEnable(GL_DEPTH_TEST)

    # ========================================================
    # GLOW
    # ========================================================

    def draw_glow(self):

        color = self.state_color()

        glDisable(GL_DEPTH_TEST)

        glBlendFunc(
            GL_SRC_ALPHA,
            GL_ONE,
        )

        for layer in range(9):

            radius = (
                0.90 +
                layer * 0.17
            )

            alpha = (
                0.020 *
                self.energy *
                (9 - layer)
            )

            glColor4f(
                color[0],
                color[1],
                color[2],
                alpha,
            )

            self.draw_flat_circle(
                radius
            )

        glBlendFunc(
            GL_SRC_ALPHA,
            GL_ONE_MINUS_SRC_ALPHA,
        )

        glEnable(GL_DEPTH_TEST)

    # ========================================================
    # FLAT CIRCLE
    # ========================================================

    def draw_flat_circle(
        self,
        radius,
    ):

        glBegin(GL_TRIANGLE_FAN)

        glVertex3f(
            0,
            0,
            0,
        )

        for i in range(
            65
        ):

            angle = (
                math.tau *
                i /
                64
            )

            glVertex3f(
                math.cos(angle) *
                radius,
                math.sin(angle) *
                radius,
                0,
            )

        glEnd()


# ============================================================
# STANDALONE TEST WINDOW
# ============================================================

class TestWindow(QMainWindow):

    def __init__(self):

        super().__init__()

        self.setWindowTitle(
            "NOVA // 3D NEURAL CORE"
        )

        self.resize(
            900,
            700,
        )

        self.core = Nova3DCore()

        self.setCentralWidget(
            self.core
        )

        # ----------------------------------------------------
        # Automatic demonstration.
        #
        # This lets us visually verify all
        # states before integrating with
        # your real UI.
        # ----------------------------------------------------

        self.demo_states = [
            "idle",
            "active",
            "listening",
            "thinking",
            "speaking",
        ]

        self.demo_index = 0

        self.demo_timer = QTimer(
            self
        )

        self.demo_timer.timeout.connect(
            self.next_demo_state
        )

        self.demo_timer.start(
            3500
        )

        self.core.set_state(
            "idle"
        )

    def next_demo_state(self):

        self.demo_index = (
            self.demo_index + 1
        ) % len(
            self.demo_states
        )

        self.core.set_state(
            self.demo_states[
                self.demo_index
            ]
        )


# ============================================================
# MAIN
# ============================================================

def main():

    app = QApplication(
        sys.argv
    )

    window = TestWindow()

    window.show()

    sys.exit(
        app.exec()
    )


if __name__ == "__main__":
    main()
"""Affichage Pygame de la carte, des vehicules, des feux et des indicateurs de simulation."""

import pygame
import math
import sys
from typing import Optional

from simulation.vehicle import VehicleState


class Renderer:
    """Dessine la simulation et gere les interactions de l utilisateur."""
    def __init__(self, network, width=1280, height=720):
        """Prepare la fenetre, les couleurs et les variables d affichage."""
        pygame.init()
        self.network = network
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Paris 13e — Traffic Simulator")

        self.clock = pygame.time.Clock()
        try:
            self.font       = pygame.font.SysFont("Arial", 14)
            self.font_small = pygame.font.SysFont("Arial", 12)
            self.font_big   = pygame.font.SysFont("Arial", 18, bold=True)
        except Exception:
            self.font = self.font_small = self.font_big = None
            print("[Renderer] Police non disponible.")

        # Vue carte
        self.zoom     = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0

        self.min_lat, self.max_lat, self.min_lon, self.max_lon = self._get_bounding_box()
        self._reset_view()

        # Références injectées par la simulation.
        self.vehicle_manager      = None
        self.light_manager        = None
        self.graph                = None
        self.metrics              = None
        self.rl_controller        = None
        self.traffic_mode: str    = "fixed"
        self.simulation_time: float = 0.0
        self.sim_speed: float     = 1.0  # multiplicateur de vitesse

        # Véhicule sélectionné à la souris.
        self.selected_vehicle_id: Optional[int] = None
        self.selected_group_id: Optional[int] = None


    def _get_bounding_box(self):
        """Calcule les limites GPS de la carte a partir des noeuds charges."""
        lats = [i.lat for i in self.network.intersections]
        lons = [i.lon for i in self.network.intersections]
        if not lats:
            lats = [s.lat for s in self.network.feux]
            lons = [s.lon for s in self.network.feux]
        if not lats:
            return 48.81, 48.84, 2.33, 2.38
        return min(lats), max(lats), min(lons), max(lons)

    def _reset_view(self):
        """Recentre la camera pour afficher toute la zone utile."""
        lat_span = self.max_lat - self.min_lat
        lon_span = self.max_lon - self.min_lon
        span = max(lat_span, lon_span) or 0.01
        self.zoom = min(self.width, self.height) / span * 0.8
        self.offset_x = self.width  / 2.0
        self.offset_y = self.height / 2.0

    def gps_to_pixel(self, lat, lon):
        """Convertit une latitude et une longitude en position ecran."""
        mid_lat = (self.min_lat + self.max_lat) / 2
        mid_lon = (self.min_lon + self.max_lon) / 2
        scale_x =  self.zoom * math.cos(math.radians(mid_lat))
        scale_y = -self.zoom
        px = (lon - mid_lon) * scale_x + self.offset_x
        py = (lat - mid_lat) * scale_y + self.offset_y
        return int(px), int(py)

    def pixel_to_gps(self, px, py):
        """Inverse de gps_to_pixel : retourne (lat, lon) pour un pixel donné."""
        mid_lat = (self.min_lat + self.max_lat) / 2
        mid_lon = (self.min_lon + self.max_lon) / 2
        scale_x =  self.zoom * math.cos(math.radians(mid_lat))
        scale_y = -self.zoom
        lon = (px - self.offset_x) / scale_x + mid_lon
        lat = (py - self.offset_y) / scale_y + mid_lat
        return lat, lon



    def draw(self):
        """Dessine une image complete de la simulation."""
        self.screen.fill((20, 22, 28))

        self._draw_roads()
        self._draw_crossings()
        self._draw_intersections()
        self._draw_traffic_lights()
        self._draw_vehicles()
        self._draw_selected_path()
        self._draw_group_highlight()
        self._draw_hud()
        self._draw_group_inspector()
        self._draw_legend()

        pygame.display.flip()

    def _draw_roads(self):
        """Trace les rues en distinguant sens unique et double sens."""
        for road in self.network.roads:
            points = []
            for nid in road.nodes:
                if nid in self.network.nodes:
                    c = self.network.nodes[nid]
                    points.append(self.gps_to_pixel(c[0], c[1]))
            if len(points) >= 2:
                if road.oneway:
                    pygame.draw.lines(self.screen, (55, 58, 70), False, points, 2)
                else:
                    offset = 2.0
                    points_aller, points_retour = [], []
                    
                    for i in range(len(points) - 1):
                        p1, p2 = points[i], points[i+1]
                        dx, dy = p2[0] - p1[0], p2[1] - p1[1]
                        length = math.hypot(dx, dy)
                        if length > 0:
                            nx, ny = -dy/length, dx/length
                            aller_p1 = (p1[0] + nx * offset, p1[1] + ny * offset)
                            aller_p2 = (p2[0] + nx * offset, p2[1] + ny * offset)
                            retour_p1 = (p1[0] - nx * offset, p1[1] - ny * offset)
                            retour_p2 = (p2[0] - nx * offset, p2[1] - ny * offset)
                            points_aller.extend([aller_p1, aller_p2] if not points_aller else [aller_p2])
                            points_retour.extend([retour_p1, retour_p2] if not points_retour else [retour_p2])

                    if len(points_aller) >= 2 and len(points_retour) >= 2:
                        pygame.draw.lines(self.screen, (65, 68, 80), False, points_aller, 1)
                        pygame.draw.lines(self.screen, (65, 68, 80), False, points_retour, 1)

    def _draw_intersections(self):
        """Affiche les points d intersection principaux de la carte."""
        for inter in self.network.intersections:
            pos = self.gps_to_pixel(inter.lat, inter.lon)
            pygame.draw.circle(self.screen, (80, 82, 95), pos, 2)

    def _draw_traffic_lights(self):
        """Dessine les feux avec leur couleur courante."""
        if self.light_manager:
            for light in self.light_manager.get_all_lights():
                pos = self.gps_to_pixel(light.lat, light.lon)
                color = light.get_color_rgb()
                outer = pygame.Rect(pos[0] - 6, pos[1] - 6, 12, 12)
                inner = pygame.Rect(pos[0] - 4, pos[1] - 4, 8, 8)
                pygame.draw.rect(self.screen, (8, 8, 10), outer)
                pygame.draw.rect(self.screen, color, inner)

                # Surbrillance des feux que l'agent vient de SWITCH
                self._draw_rl_switch_overlay(light, pos)
        else:
            for signal in self.network.feux:
                pos = self.gps_to_pixel(signal.lat, signal.lon)
                pygame.draw.rect(self.screen, (220, 50, 50),
                                 (pos[0] - 4, pos[1] - 4, 8, 8))

    def _draw_rl_switch_overlay(self, light, pos):
        """Anneau cyan pulsant pendant ~3s après un SWITCH de l'agent."""
        if self.rl_controller is None or light.group_id is None:
            return

        elapsed = self.rl_controller.time_since_switch(light.group_id)
        if elapsed is None:
            return

        fade_duration = 3.0
        if elapsed > fade_duration:
            return

        alpha_ratio = 1.0 - (elapsed / fade_duration)
        radius = int(10 + 4 * alpha_ratio)
        thickness = max(1, int(2 + alpha_ratio))
        # Cyan vif qui s'estompe progressivement (composantes clampées 0..255)
        ring_color = (
            min(255, int(80 * alpha_ratio + 30)),
            min(255, int(220 * alpha_ratio + 35)),
            min(255, int(255 * alpha_ratio + 40)),
        )
        pygame.draw.circle(self.screen, ring_color, pos, radius, thickness)

    def _draw_group_highlight(self):
        """Cercle jaune autour du carrefour sélectionné."""
        if self.selected_group_id is None or self.light_manager is None:
            return
        grp = self.light_manager.get_groups().get(self.selected_group_id)
        if grp is None:
            return
        cx, cy = self.gps_to_pixel(grp.center_lat, grp.center_lon)
        pygame.draw.circle(self.screen, (255, 220, 80), (cx, cy), 28, 3)
        pygame.draw.circle(self.screen, (255, 220, 80), (cx, cy), 4)

    def _draw_group_inspector(self):
        """Panneau d'inspection détaillée du carrefour sélectionné."""
        if self.selected_group_id is None or self.light_manager is None:
            return
        if self.font is None:
            return

        gid = self.selected_group_id
        grp = self.light_manager.get_groups().get(gid)
        if grp is None:
            return

        lights_A = self.light_manager.get_group_lights(gid, "A")
        lights_B = self.light_manager.get_group_lights(gid, "B")

        # On résume l'état de chaque phase
        def phase_summary(lights):
            """Resume la phase affichee dans le panneau du carrefour."""
            if not lights:
                return "—"
            l = lights[0]
            return (f"{l.state.value:<6} "
                    f"({l.time_in_phase:5.1f}s / "
                    f"reste {l.time_remaining:5.1f}s)")

        lines = [
            f"CARREFOUR #{gid}",
            f"GPS : {grp.center_lat:.5f}, {grp.center_lon:.5f}",
            f"Feux : {len(lights_A)} (phase A)  +  {len(lights_B)} (phase B)",
            f"Phase A : {phase_summary(lights_A)}",
            f"Phase B : {phase_summary(lights_B)}",
        ]

        # Files d'attente courantes (depuis les métriques)
        if self.metrics is not None and self.metrics.latest_observation is not None:
            obs_by_id = self.metrics.latest_observation.lights
            queue_A = sum(obs_by_id[l.node_id].queue_length
                          for l in lights_A if l.node_id in obs_by_id)
            queue_B = sum(obs_by_id[l.node_id].queue_length
                          for l in lights_B if l.node_id in obs_by_id)
            wait_A = max((obs_by_id[l.node_id].oldest_wait_s
                          for l in lights_A if l.node_id in obs_by_id),
                         default=0.0)
            wait_B = max((obs_by_id[l.node_id].oldest_wait_s
                          for l in lights_B if l.node_id in obs_by_id),
                         default=0.0)
            lines.append(f"File A : {queue_A:>3} véh   "
                         f"attente max : {wait_A:5.1f}s")
            lines.append(f"File B : {queue_B:>3} véh   "
                         f"attente max : {wait_B:5.1f}s")

        # Infos agent RL si présent
        if self.rl_controller is not None:
            elapsed = self.rl_controller.time_since_switch(gid)
            if elapsed is None:
                lines.append("Agent RL : aucun SWITCH récent")
            else:
                lines.append(f"Agent RL : SWITCH il y a {elapsed:.1f}s")

        lines.append("")
        lines.append("Clic droit pour désélectionner")

        # Rendu du panneau en bas-droite
        text_surfs = [
            self.font.render(line, True, (220, 225, 240))
            for line in lines
        ]
        bg_width  = max(s.get_width() for s in text_surfs) + 20
        bg_height = sum(s.get_height() for s in text_surfs) + 14
        x = self.width - bg_width - 10
        y = self.height - bg_height - 30

        bg = pygame.Surface((bg_width, bg_height))
        bg.set_alpha(200)
        bg.fill((10, 12, 18))
        self.screen.blit(bg, (x, y))
        pygame.draw.rect(self.screen, (255, 220, 80),
                         (x, y, bg_width, bg_height), 1)

        cy = y + 7
        for surf in text_surfs:
            self.screen.blit(surf, (x + 10, cy))
            cy += surf.get_height()

    def _draw_crossings(self):
        """Affiche les passages pietons issus des donnees cartographiques."""
        for crossing in self.network.passages:
            pos = self.gps_to_pixel(crossing.lat, crossing.lon)
            color = (0, 180, 200) if crossing.is_regulated else (140, 140, 140)
            pygame.draw.rect(self.screen, color, (pos[0] - 2, pos[1] - 2, 4, 4), 1)

    def _draw_vehicles(self):
        """Dessine tous les vehicules encore actifs dans la simulation."""
        if self.vehicle_manager is None:
            return

        for vehicle in self.vehicle_manager.get_vehicle_list():
            pos = self._vehicle_pixel(vehicle)

            # Les véhicules gardent des couleurs différentes des feux.
            if vehicle.state == VehicleState.STOPPED:
                outline_color = (225, 230, 240)
                body_color = (120, 130, 150)
            elif vehicle.state == VehicleState.BRAKING:
                outline_color = (245, 170, 70)
                body_color = (250, 205, 95)
            else:
                outline_color = (80, 170, 255)
                body_color = (105, 200, 255)

            pygame.draw.circle(self.screen, outline_color, pos, 6)
            pygame.draw.circle(self.screen, body_color, pos, 4)

            if vehicle.waiting_at_light:
                pygame.draw.rect(self.screen, (255, 80, 80),
                                 (pos[0] - 2, pos[1] - 11, 4, 4))

    def _vehicle_pixel(self, vehicle):
        """Calcule la position ecran d un vehicule, meme quand il est range dans une file."""
        pos = self.gps_to_pixel(vehicle.lat, vehicle.lon)
        if self.graph is None or vehicle.seg_oneway:
            return pos

        from_node = self.graph.nodes.get(vehicle.seg_from)
        to_node = self.graph.nodes.get(vehicle.seg_to)
        if from_node is None or to_node is None:
            return pos

        p1 = self.gps_to_pixel(from_node.lat, from_node.lon)
        p2 = self.gps_to_pixel(to_node.lat, to_node.lon)
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        length = math.hypot(dx, dy)
        if length <= 1e-6:
            return pos

        lane_offset = 4.0
        nx = -dy / length
        ny = dx / length
        return int(pos[0] + nx * lane_offset), int(pos[1] + ny * lane_offset)

    def _draw_selected_path(self):
        """Affiche le trajet du véhicule sélectionné."""
        if self.vehicle_manager is None or self.selected_vehicle_id is None:
            return
        vehicle = self.vehicle_manager.vehicles.get(self.selected_vehicle_id)
        if vehicle is None or not vehicle.path or self.graph is None:
            return

        coords = self.graph.get_path_coordinates(vehicle.path)
        if len(coords) < 2:
            return

        pixels = [self.gps_to_pixel(lat, lon) for lat, lon in coords]
        pygame.draw.lines(self.screen, (0, 150, 255), False, pixels, 2)

        # Origine et destination du trajet.
        if pixels:
            pygame.draw.rect(self.screen, (0, 255, 80),
                             (pixels[0][0] - 4, pixels[0][1] - 4, 8, 8))
            pygame.draw.rect(self.screen, (255, 60, 60),
                             (pixels[-1][0] - 4, pixels[-1][1] - 4, 8, 8))



    def _draw_hud(self):
        """Affiche les informations de temps, vitesse et trafic en haut de l ecran."""
        if self.font is None:
            return

        mins  = int(self.simulation_time) // 60
        secs  = int(self.simulation_time) % 60
        fps   = int(self.clock.get_fps())

        if self.vehicle_manager:
            stats = self.vehicle_manager.get_stats()
            hud_text = (
                f"Temps : {mins:02d}:{secs:02d}  |  "
                f"Vitesse ×{self.sim_speed:.1f}  |  "
                f"FPS : {fps}  |  "
                f"Véhicules : {stats['total']}  "
                f"(▶ {stats['moving']}  ⏸ {stats['stopped']}   {stats['arrived']})  |  "
                f"Files : {stats['queued']}  max {stats['max_queue']}"
            )
            hud_lines = [hud_text]
            if self.metrics is not None:
                live = self.metrics.live_stats()
                hud_lines.append(
                    f"Mode : {self.traffic_mode}  |  "
                    f"Débit : {live['throughput_per_min']:.1f}/min  |  "
                    f"File moy. : {live['avg_queue_length']:.1f}  |  "
                    f"ρ max : {live['max_saturation']:.2f}  |  "
                    f"Pression max : {live['max_pressure']:.1f}"
                )
            if self.rl_controller is not None:
                rl_stats = self.rl_controller.stats()
                hud_lines.append(
                    f"Agent RL  |  "
                    f"Q-table : {rl_stats['qtable_size']} états  |  "
                    f"KEEP : {rl_stats['keep_count']}  |  "
                    f"SWITCH : {rl_stats['switch_count']} "
                    f"({rl_stats['switch_ratio'] * 100:.0f}%)  |  "
                    f"prochaine décision dans "
                    f"{max(0.0, rl_stats['step_dt'] - rl_stats['since_decision']):.1f}s"
                )
        else:
            hud_text = (
                f"Temps : {mins:02d}:{secs:02d}  |  "
                f"FPS : {fps}  |  "
                f"Routes : {len(self.network.roads)}"
            )
            hud_lines = [hud_text]

        text_surfs = [
            self.font.render(line, True, (210, 215, 230))
            for line in hud_lines
        ]
        bg_width = max(surf.get_width() for surf in text_surfs) + 20
        bg_height = sum(surf.get_height() for surf in text_surfs) + 10
        bg = pygame.Surface((bg_width, bg_height))
        bg.set_alpha(160)
        bg.fill((15, 15, 20))
        self.screen.blit(bg, (5, 5))
        y = 9
        for surf in text_surfs:
            self.screen.blit(surf, (15, y))
            y += surf.get_height()

        keys_text = ("WASD/Flèches: pan  |  Molette: zoom  |  R: reset vue  |  "
                     "+/-: vitesse  |  N: nouveau véhicule  |  "
                     "Clic gauche: inspecter feu/voiture  |  Clic droit: désélectionner  |  "
                     "Échap: quitter")
        k_surf = self.font_small.render(keys_text, True, (130, 135, 150))
        self.screen.blit(k_surf, (10, self.height - 20))


    def _draw_legend(self):
        """Affiche la legende des couleurs et des symboles."""
        if self.font_small is None:
            return

        x, y = 10, self.height - 160
        w, h = 255, 132

        bg = pygame.Surface((w, h))
        bg.set_alpha(175)
        bg.fill((15, 15, 20))
        self.screen.blit(bg, (x, y))

        items = [
            ((55, 58, 70),   "route", "Route sens unique"),
            ((65, 68, 80),   "double", "Route double sens"),
            ((80, 82, 95),   "dot",   "Intersection"),
            ((50, 200, 50),  "light", "Feu — vert"),
            ((220, 50, 50),  "light", "Feu — rouge"),
            ((220, 180, 50), "light", "Feu — orange"),
            ((105, 200, 255), "car",  "Véhicule en mouvement"),
            ((120, 130, 150), "car",  "Véhicule arrêté"),
            ((0, 180, 200),  "sq",    "Passage piéton"),
        ]

        for i, (color, shape, label) in enumerate(items):
            iy = y + 8 + i * 14
            cx = x + 18
            if shape == "route":
                pygame.draw.line(self.screen, color, (cx - 8, iy + 6), (cx + 8, iy + 6), 2)
            elif shape == "double":
                pygame.draw.line(self.screen, color, (cx - 8, iy + 4), (cx + 8, iy + 4), 1)
                pygame.draw.line(self.screen, color, (cx - 8, iy + 8), (cx + 8, iy + 8), 1)
            elif shape == "dot":
                pygame.draw.circle(self.screen, color, (cx, iy + 6), 5)
            elif shape == "light":
                pygame.draw.rect(self.screen, color, (cx - 4, iy + 2, 8, 8))
            elif shape == "car":
                pygame.draw.circle(self.screen, (80, 170, 255), (cx, iy + 6), 6)
                pygame.draw.circle(self.screen, color, (cx, iy + 6), 4)
            elif shape == "sq":
                pygame.draw.rect(self.screen, color, (cx - 4, iy + 2, 9, 9), 1)

            txt = self.font_small.render(label, True, (200, 205, 220))
            self.screen.blit(txt, (x + 32, iy))



    def handle_events(self):
        """Gère les entrées clavier et souris."""
        actions = {"spawn": False, "quit": False, "speed_up": False, "speed_down": False}

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                actions["quit"] = True

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:
                    self.zoom *= 1.15
                elif event.button == 5:
                    self.zoom /= 1.15
                elif event.button == 1:
                    if not self._try_select_vehicle(event.pos):
                        self._try_select_group(event.pos)
                elif event.button == 3:
                    self.selected_vehicle_id = None
                    self.selected_group_id = None

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    actions["quit"] = True
                elif event.key == pygame.K_r:
                    self._reset_view()
                elif event.key in (pygame.K_PLUS, pygame.K_KP_PLUS, pygame.K_EQUALS):
                    actions["speed_up"] = True
                elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS):
                    actions["speed_down"] = True
                elif event.key == pygame.K_n:
                    actions["spawn"] = True

        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: self.offset_x += 8
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: self.offset_x -= 8
        if keys[pygame.K_UP]    or keys[pygame.K_w]: self.offset_y += 8
        if keys[pygame.K_DOWN]  or keys[pygame.K_s]: self.offset_y -= 8

        return actions

    def _try_select_vehicle(self, mouse_pos) -> bool:
        """Sélectionne le véhicule le plus proche du clic. True si trouvé."""
        if self.vehicle_manager is None:
            return False
        best_id   = None
        best_dist = 15  # pixels
        for vid, v in self.vehicle_manager.vehicles.items():
            px, py = self._vehicle_pixel(v)
            d = math.hypot(px - mouse_pos[0], py - mouse_pos[1])
            if d < best_dist:
                best_dist = d
                best_id = vid
        if best_id is not None:
            self.selected_vehicle_id = best_id
            self.selected_group_id = None
            return True
        return False

    def _try_select_group(self, mouse_pos) -> bool:
        """Sélectionne le carrefour (IntersectionGroup) le plus proche du clic."""
        if self.light_manager is None:
            return False
        groups = self.light_manager.get_groups()
        if not groups:
            return False
        best_id   = None
        best_dist = 60  # pixels
        for gid, grp in groups.items():
            gx, gy = self.gps_to_pixel(grp.center_lat, grp.center_lon)
            d = math.hypot(gx - mouse_pos[0], gy - mouse_pos[1])
            if d < best_dist:
                best_dist = d
                best_id = gid
        if best_id is not None:
            self.selected_group_id = best_id
            self.selected_vehicle_id = None
            return True
        return False

   

    def run(self):
        """Mode de base : visualisation statique du réseau."""
        while True:
            actions = self.handle_events()
            if actions.get("quit"):
                pygame.quit()
                sys.exit()
            self.draw()
            self.clock.tick(60)

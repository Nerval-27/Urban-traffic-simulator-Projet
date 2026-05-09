
import pygame
import math
import sys
from typing import Optional

from vehicle import VehicleState


class Renderer:
    def __init__(self, network, width=1280, height=720):
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
        self.traffic_mode: str    = "fixed"
        self.simulation_time: float = 0.0
        self.sim_speed: float     = 1.0  # multiplicateur de vitesse

        # Véhicule sélectionné à la souris.
        self.selected_vehicle_id: Optional[int] = None


    def _get_bounding_box(self):
        lats = [i.lat for i in self.network.intersections]
        lons = [i.lon for i in self.network.intersections]
        if not lats:
            lats = [s.lat for s in self.network.feux]
            lons = [s.lon for s in self.network.feux]
        if not lats:
            return 48.81, 48.84, 2.33, 2.38
        return min(lats), max(lats), min(lons), max(lons)

    def _reset_view(self):
        lat_span = self.max_lat - self.min_lat
        lon_span = self.max_lon - self.min_lon
        span = max(lat_span, lon_span) or 0.01
        self.zoom = min(self.width, self.height) / span * 0.8
        self.offset_x = self.width  / 2.0
        self.offset_y = self.height / 2.0

    def gps_to_pixel(self, lat, lon):
        mid_lat = (self.min_lat + self.max_lat) / 2
        mid_lon = (self.min_lon + self.max_lon) / 2
        scale_x =  self.zoom * math.cos(math.radians(mid_lat))
        scale_y = -self.zoom
        px = (lon - mid_lon) * scale_x + self.offset_x
        py = (lat - mid_lat) * scale_y + self.offset_y
        return int(px), int(py)



    def draw(self):
        self.screen.fill((20, 22, 28))

        self._draw_roads()
        self._draw_crossings()
        self._draw_intersections()
        self._draw_traffic_lights()
        self._draw_vehicles()
        self._draw_selected_path()
        self._draw_hud()
        self._draw_legend()

        pygame.display.flip()

    def _draw_roads(self):
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
        else:
            # Affichage simple quand le gestionnaire n'est pas encore branché.
            for signal in self.network.feux:
                pos = self.gps_to_pixel(signal.lat, signal.lon)
                pygame.draw.rect(self.screen, (220, 50, 50),
                                 (pos[0] - 4, pos[1] - 4, 8, 8))

    def _draw_crossings(self):
        for crossing in self.network.passages:
            pos = self.gps_to_pixel(crossing.lat, crossing.lon)
            color = (0, 180, 200) if crossing.is_regulated else (140, 140, 140)
            pygame.draw.rect(self.screen, color, (pos[0] - 2, pos[1] - 2, 4, 4), 1)

    def _draw_vehicles(self):
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

        keys_text = "WASD/Flèches: pan  |  Molette: zoom  |  R: reset vue  |  +/-: vitesse  |  N: nouveau véhicule  |  Échap: quitter"
        k_surf = self.font_small.render(keys_text, True, (130, 135, 150))
        self.screen.blit(k_surf, (10, self.height - 20))


    def _draw_legend(self):
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
                    self._try_select_vehicle(event.pos)

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

    def _try_select_vehicle(self, mouse_pos):
        """Sélectionne le véhicule le plus proche du clic."""
        if self.vehicle_manager is None:
            return
        best_id   = None
        best_dist = 15  # pixels
        for vid, v in self.vehicle_manager.vehicles.items():
            px, py = self._vehicle_pixel(v)
            d = math.hypot(px - mouse_pos[0], py - mouse_pos[1])
            if d < best_dist:
                best_dist = d
                best_id = vid
        self.selected_vehicle_id = best_id

   

    def run(self):
        """Mode de base : visualisation statique du réseau."""
        while True:
            actions = self.handle_events()
            if actions.get("quit"):
                pygame.quit()
                sys.exit()
            self.draw()
            self.clock.tick(60)

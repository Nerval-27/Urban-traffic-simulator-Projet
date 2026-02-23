import pygame
import math
import sys

class Renderer:
    def __init__(self, network, width=1280, height=720):
        pygame.init()
        self.network = network
        self.width = width
        self.height = height
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("Paris 13e - Traffic Simulator")
        
        self.clock = pygame.time.Clock()
        try:
            self.font = pygame.font.SysFont("Arial", 16)
        except:
            self.font = None
            print("Erreur police, pas de texte affiché.")
        
        # État du rendu (zoom et pan)
        self.zoom = 1.0
        self.offset_x = 0
        self.offset_y = 0
        
        # Calcul de la bounding box GPS
        self.min_lat, self.max_lat, self.min_lon, self.max_lon = self._get_bounding_box()
        
        # Ajustement initial pour centrer
        self._reset_view()

    def _get_bounding_box(self):
        lats = [i.lat for i in self.network.intersections]
        lons = [i.lon for i in self.network.intersections]
        
        # Si pas d'intersections, on regarde les feux ou crossings
        if not lats:
            lats = [s.lat for s in self.network.traffic_signals]
            lons = [s.lon for s in self.network.traffic_signals]
            
        if not lats:
            return 48.81, 48.84, 2.33, 2.38 # Par défaut Paris 13
            
        return min(lats), max(lats), min(lons), max(lons)

    def _reset_view(self):
        self.zoom = min(self.width, self.height) / max(self.max_lat - self.min_lat, self.max_lon - self.min_lon) * 0.8
        self.offset_x = self.width / 2
        self.offset_y = self.height / 2

    def gps_to_pixel(self, lat, lon):
        # Inversion Y car Pygame 0 est en haut
        # On centre sur la moyenne
        mid_lat = (self.min_lat + self.max_lat) / 2
        mid_lon = (self.min_lon + self.max_lon) / 2
        
        # Échelle approximative pour que 1 deg lat ~ 1 deg lon à Paris (Mercator local)
        scale_x = self.zoom * math.cos(math.radians(mid_lat))
        scale_y = -self.zoom # Négatif car Y descend
        
        px = (lon - mid_lon) * scale_x + self.offset_x
        py = (lat - mid_lat) * scale_y + self.offset_y
        
        return int(px), int(py)

    def draw(self):
        self.screen.fill((30, 30, 30)) # Gris foncé
        
        # Dessin des routes
        for road in self.network.roads:
            points = []
            for nid in road.nodes:
                if nid in self.network.nodes:
                    coords = self.network.nodes[nid]
                    points.append(self.gps_to_pixel(coords[0], coords[1]))
            
            if len(points) >= 2:
                pygame.draw.lines(self.screen, (80, 80, 80), False, points, 2)
        
        # Dessin des intersections
        for inter in self.network.intersections:
            pos = self.gps_to_pixel(inter.lat, inter.lon)
            pygame.draw.circle(self.screen, (100, 100, 100), pos, 3)
            
        # Dessin des feux
        for signal in self.network.feux:
            pos = self.gps_to_pixel(signal.lat, signal.lon)
            pygame.draw.circle(self.screen, (255, 50, 50), pos, 4)
            
        # Dessin des passages piétons
        for crossing in self.network.passages:
            pos = self.gps_to_pixel(crossing.lat, crossing.lon)
            color = (0, 200, 200) if crossing.is_regulated else (180, 180, 180)
            pygame.draw.rect(self.screen, color, (pos[0]-2, pos[1]-2, 4, 4), 1)

        # HUD
        if self.font:
            info = f"Zoom: {self.zoom:.2f} | Routes: {len(self.network.roads)} | Piétons: {len(self.network.passages)} | FPS: {int(self.clock.get_fps())}"
            text = self.font.render(info, True, (200, 200, 200))
            self.screen.blit(text, (10, 10))

        self.draw_legend()

        pygame.display.flip()

    def draw_legend(self):
        if not self.font:
            return
            
        # Position de la légende (bas gauche)
        x, y = 10, self.height - 110
        width, height = 220, 100
        
        # Fond semi-transparent
        s = pygame.Surface((width, height))
        s.set_alpha(180)
        s.fill((20, 20, 20))
        self.screen.blit(s, (x, y))
        
        items = [
            ((80, 80, 80), "Route (Ligne)"),
            ((100, 100, 100), "Intersection (Cercle gris)"),
            ((255, 50, 50), "Feu de circulation (Point rouge)"),
            ((0, 200, 200), "Passage piéton (Régulé)"),
            ((180, 180, 180), "Passage piéton (Simple)")
        ]
        
        for i, (color, label) in enumerate(items):
            # Dessin de l'icône/couleur
            iy = y + 10 + i*18
            if "Ligne" in label:
                pygame.draw.line(self.screen, color, (x+10, iy+8), (x+25, iy+8), 2)
            elif "Cercle" in label or "Point" in label:
                pygame.draw.circle(self.screen, color, (x+17, iy+8), 4)
            else:
                pygame.draw.rect(self.screen, color, (x+12, iy+4, 10, 10), 1)
                
            # Texte
            txt = self.font.render(label, True, (220, 220, 220))
            self.screen.blit(txt, (x + 35, iy))

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 4:
                    self.zoom *= 1.2
                elif event.button == 5: 
                    self.zoom /= 1.2
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
        
        # Pan avec les touches
        keys = pygame.key.get_pressed()
        step = 10 / (self.zoom / 1000 if self.zoom > 0 else 1)
        if keys[pygame.K_LEFT] or keys[pygame.K_a]: self.offset_x += 10
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: self.offset_x -= 10
        if keys[pygame.K_UP] or keys[pygame.K_w]: self.offset_y += 10
        if keys[pygame.K_DOWN] or keys[pygame.K_s]: self.offset_y -= 10

    def run(self):
        while True:
            self.handle_events()
            self.draw()
            self.clock.tick(60)

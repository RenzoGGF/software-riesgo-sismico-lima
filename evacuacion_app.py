import tkinter
from tkinter import ttk, messagebox
import tkintermapview
import pandas as pd
import networkx as nx
from scipy.spatial import KDTree
import os
import threading
from queue import Queue, Empty
import math
import geojson
import time

class MapViewFrame(tkinter.Frame):
    def __init__(self, master, app_controller, algorithm_choice: str):
        super().__init__(master)
        self.app = app_controller
        self.algorithm_choice = algorithm_choice
        self.algorithm_info = {
            "dijkstra": {"name": "Dijkstra", "color": "#E63946", "type": "route"},
            "astar": {"name": "A*", "color": "#E63946", "type": "route"},
            "centrality": {"name": "Análisis de Puntos Críticos", "color": "#E63946", "type": "network_analysis"}
        }
        self.configure(bg="#ECECEC")
        
        top_frame = ttk.Frame(self, padding="5 5 5 5")
        top_frame.pack(fill="x")
        back_button = ttk.Button(top_frame, text="◄ Volver al Menú", command=self.app.show_menu, style="Accent.TButton")
        back_button.pack(side="left", padx=5)
        algo_name = self.algorithm_info[self.algorithm_choice]["name"]
        self.status_label = ttk.Label(top_frame, text=f"Algoritmo: {algo_name}. Cargando datos...", font=("Helvetica", 11), anchor="w")
        self.status_label.pack(side="left", padx=10, expand=True, fill="x")
        self.map_widget = tkintermapview.TkinterMapView(self, width=980, height=720, corner_radius=0)
        self.map_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        self.G_undirected, self.G_dirigido, self.pos_nodos, self.kd_tree_nodos, self.df_nodos = None, None, None, None, None
        self.puntos_seguros_data = []
        self.puntos_seguros_markers = {}
        self.origen_marker, self.destino_marker = None, None
        self.drawn_elements = []
        self.last_destination_info = None
        self.gui_queue = Queue()
        
        self.process_gui_queue()
        threading.Thread(target=self.cargar_datos_iniciales, daemon=True).start()

    def process_gui_queue(self):
        try:
            while not self.gui_queue.empty():
                task, args = self.gui_queue.get_nowait()
                task(*args)
        except Empty: pass
        finally: self.after(100, self.process_gui_queue)

    def dibujar_limites_distritales_geojson(self):
        distritos_de_interes = ["SAN ISIDRO", "MIRAFLORES", "SURQUILLO", "SAN BORJA", "BARRANCO", "SANTIAGO DE SURCO"]
        geojson_path = "peru_distrital_simple.geojson"
        if not os.path.exists(geojson_path):
            self.set_status_text(f"Advertencia: No se encontró '{geojson_path}'.")
            return
        try:
            with open(geojson_path, "r", encoding="utf-8") as f:
                geojson_data = geojson.load(f)
            for feature in geojson_data['features']:
                properties = feature.get('properties', {})
                if properties.get('NOMBPROV', '').upper() == 'LIMA' and properties.get('NOMBDIST', '').upper() in distritos_de_interes:
                    geometria = feature.get('geometry')
                    if not geometria: continue
                    geometries = [geometria['coordinates']] if geometria['type'] == 'Polygon' else geometria.get('coordinates', [])
                    for geometry_coords in geometries:
                        coordenadas_exteriores = geometry_coords[0]
                        if len(coordenadas_exteriores) > 1:
                            coordenadas_corregidas = [(c[1], c[0]) for c in coordenadas_exteriores]
                            self.map_widget.set_path(coordenadas_corregidas, color="#0004FF", width=1)
        except Exception as e:
            self.set_status_text(f"Error al leer archivo de límites: {e}")

    def cargar_datos_iniciales(self):
        try:
            self.set_status_text("Cargando y procesando datos...")
            nodos_path = "nodos_lima.csv"
            aristas_path = "calles_lima_con_vulnerabilidad.csv"
            puntos_path = "puntos_seguros.csv"
            
            df_nodos_full = pd.read_csv(nodos_path)
            df_nodos_full.dropna(subset=['lat', 'lon'], inplace=True)
            df_aristas = pd.read_csv(aristas_path)
            df_puntos_seguros = pd.read_csv(puntos_path)
            
            G_full_undirected = nx.Graph()
            G_full_directed = nx.DiGraph()

            for _, arista in df_aristas.iterrows():
                velocidad_kmh = arista.get('velocidad_max', 30)
                if not isinstance(velocidad_kmh, (int, float)) or velocidad_kmh <= 0:
                    velocidad_kmh = 30
                distancia_km = arista['longitud'] / 1000
                tiempo_en_minutos = (distancia_km / velocidad_kmh) * 60
                penalizacion_riesgo = 1 + (arista.get('vulnerabilidad', 0) * 2.0)
                peso = tiempo_en_minutos * penalizacion_riesgo
                
                origen, destino = arista['origen'], arista['destino']
                G_full_undirected.add_edge(origen, destino, weight=peso)
                G_full_directed.add_edge(origen, destino, weight=peso)
                if not arista.get('sentido_unico', False):
                    G_full_directed.add_edge(destino, origen, weight=peso)

            main_component_nodes = max(nx.connected_components(G_full_undirected), key=len)
            
            self.G_undirected = G_full_undirected.subgraph(main_component_nodes).copy()
            self.G_dirigido = G_full_directed.subgraph(main_component_nodes).copy()

            self.df_nodos = df_nodos_full[df_nodos_full['id'].isin(main_component_nodes)]
            self.kd_tree_nodos = KDTree(self.df_nodos[['lat', 'lon']].values)
            self.pos_nodos = {n['id']: (n['lat'], n['lon']) for _, n in self.df_nodos.iterrows()}
            self.puntos_seguros_data = [p.to_dict() for _, p in df_puntos_seguros.iterrows() if self.encontrar_nodo_cercano(p["lat"], p["lon"]) in self.G_undirected]
            
            self.gui_queue.put((self.setup_map, ()))
        except Exception as e:
            self.gui_queue.put((self.set_status_text, (f"Error fatal al cargar datos: {e}",)))

    def setup_map(self):
        self.dibujar_limites_distritales_geojson()
        for punto in self.puntos_seguros_data:
            marker = self.map_widget.set_marker(punto["lat"], punto["lon"], text=punto["nombre"], text_color="#2E603A", marker_color_circle="#588157", marker_color_outside="#2E603A")
            self.puntos_seguros_markers[(punto["lat"], punto["lon"])] = marker
        
        self.map_widget.set_position(-12.119, -77.021)
        self.map_widget.set_zoom(14)
        
        algo_type = self.algorithm_info[self.algorithm_choice]['type']
        algo_name = self.algorithm_info[self.algorithm_choice]['name']
        
        if algo_type == 'route':
            self.map_widget.add_left_click_map_command(self.on_map_click_route)
            self.set_status_text(f"Algoritmo: {algo_name}. Haz clic para elegir tu ubicación.")
        elif algo_type == 'network_analysis':
            self.set_status_text(f"Calculando {algo_name}... Esto puede tardar unos segundos.")
            threading.Thread(target=self.calcular_y_dibujar_puntos_criticos, daemon=True).start()

    def set_status_text(self, text):
        self.status_label.config(text=text)

    def limpiar_mapa(self):
        for element in self.drawn_elements:
            element.delete()
        self.drawn_elements = []
        if self.origen_marker: self.origen_marker.delete()
        if self.destino_marker: self.destino_marker.delete()
        self.origen_marker, self.destino_marker = None, None

    def on_map_click_route(self, coords):
        self.limpiar_mapa()
        self.origen_marker = self.map_widget.set_marker(coords[0], coords[1], text="Tu Ubicación")
        algo_name = self.algorithm_info[self.algorithm_choice]["name"]
        self.set_status_text(f"Calculando ruta con {algo_name} desde ({coords[0]:.4f}, {coords[1]:.4f})...")
        threading.Thread(target=self.encontrar_y_dibujar_ruta, args=(coords[0], coords[1]), daemon=True).start()
        
    def encontrar_nodo_cercano(self, lat, lon):
        _, indice = self.kd_tree_nodos.query([lat, lon])
        return self.df_nodos.iloc[indice]['id']
    
    def astar_heuristic(self, u, v):
        pos_u, pos_v = self.pos_nodos[u], self.pos_nodos[v]
        return math.sqrt((pos_u[0] - pos_v[0])**2 + (pos_u[1] - pos_v[1])**2)

    def encontrar_y_dibujar_ruta(self, origen_lat, origen_lon):
        if self.G_dirigido is None: return
        try:
            start_time = time.time()
            nodo_origen = self.encontrar_nodo_cercano(origen_lat, origen_lon)
            mejor_tiempo, mejor_destino_info = float('inf'), None
            
            if self.algorithm_choice == "dijkstra":
                distancias = nx.single_source_dijkstra_path_length(self.G_dirigido, source=nodo_origen, weight='weight')
                for punto in self.puntos_seguros_data:
                    nodo_destino = self.encontrar_nodo_cercano(punto["lat"], punto["lon"])
                    if nodo_destino in distancias and distancias[nodo_destino] < mejor_tiempo:
                        mejor_tiempo, mejor_destino_info = distancias[nodo_destino], punto
            
            elif self.algorithm_choice == "astar":
                for punto in self.puntos_seguros_data:
                    try:
                        nodo_destino = self.encontrar_nodo_cercano(punto["lat"], punto["lon"])
                        if nodo_origen == nodo_destino: continue
                        tiempo = nx.astar_path_length(self.G_dirigido, source=nodo_origen, target=nodo_destino, heuristic=self.astar_heuristic, weight='weight')
                        if tiempo < mejor_tiempo: mejor_tiempo, mejor_destino_info = tiempo, punto
                    except (nx.NetworkXNoPath, nx.NodeNotFound): continue
            
            if mejor_destino_info is None:
                self.gui_queue.put((self.set_status_text, ("No se encontró ruta a ningún punto seguro.",))); return

            final_nodo_destino = self.encontrar_nodo_cercano(mejor_destino_info["lat"], mejor_destino_info["lon"])
            
            path_finder = nx.dijkstra_path
            path_args = {'weight': 'weight'}
            if self.algorithm_choice == 'astar':
                path_finder = nx.astar_path
                path_args['heuristic'] = self.astar_heuristic

            ruta_nodos = path_finder(self.G_dirigido, source=nodo_origen, target=final_nodo_destino, **path_args)
            
            end_time = time.time()
            calc_time = end_time - start_time

            if not ruta_nodos: raise ValueError("El algoritmo no devolvió ninguna ruta.")
            
            path_coords = [self.pos_nodos[nodo] for nodo in ruta_nodos]
            self.gui_queue.put((self.dibujar_ruta, (path_coords, mejor_destino_info, mejor_tiempo, calc_time)))
        except Exception as e:
            self.gui_queue.put((self.set_status_text, (f"Error al calcular la ruta: {e}",)))

    def calcular_y_dibujar_puntos_criticos(self):
        if self.G_undirected is None: return
        try:
            start_time = time.time()
            centrality = nx.betweenness_centrality(self.G_undirected, k=100, normalized=True, weight='weight')
            
            nodos_criticos = sorted(centrality, key=centrality.get, reverse=True)[:50]
            end_time = time.time()
            calc_time = end_time - start_time
            
            self.gui_queue.put((self.dibujar_puntos_criticos, (nodos_criticos, calc_time)))

        except Exception as e:
            self.gui_queue.put((self.set_status_text, (f"Error al calcular puntos críticos: {e}",)))

    def dibujar_ruta(self, path_coords, destino_info, costo, calc_time):
        self.limpiar_mapa()
        info = self.algorithm_info[self.algorithm_choice]
        path = self.map_widget.set_path(path_coords, color=info["color"], width=4)
        self.drawn_elements.append(path)
        
        self.destino_marker = self.map_widget.set_marker(destino_info["lat"], destino_info["lon"], text=f"Destino: {destino_info['nombre']}", text_color="#A4161A", marker_color_circle="#E63946", marker_color_outside="#A4161A")
        self.last_destination_info = destino_info
        self.set_status_text(f"Ruta a {destino_info['nombre']} encontrada en {calc_time:.2f}s. Costo: {costo:.2f} min.")

    def create_circle_polygon(self, lat, lon, radius_meters, num_points=20):
        coords = []
        radius_lat = radius_meters / 111320.0
        radius_lon = radius_meters / (111320.0 * math.cos(math.radians(lat)))
        for i in range(num_points + 1):
            angle = math.radians(i * (360 / num_points))
            dx = radius_lon * math.cos(angle)
            dy = radius_lat * math.sin(angle)
            coords.append((lat + dy, lon + dx))
        return coords

    def dibujar_puntos_criticos(self, nodos_criticos, calc_time):
        self.limpiar_mapa()
        info = self.algorithm_info[self.algorithm_choice]
        
        for i, nodo_id in enumerate(nodos_criticos):
            pos = self.pos_nodos[nodo_id]
            
            circle_coords = self.create_circle_polygon(pos[0], pos[1], radius_meters=50)
            polygon = self.map_widget.set_polygon(
                circle_coords,
                fill_color=info['color'],
                outline_color=info['color'],
                border_width=2,
                name=f"critical_circle_{i}"
            )
            self.drawn_elements.append(polygon)
            
        self.set_status_text(f"Análisis de {len(nodos_criticos)} puntos críticos completado en {calc_time:.2f}s.")


class App(tkinter.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Rutas y Análisis de Redes")
        self.geometry("1100x800")
        self.minsize(800, 600)
        self.configure(bg="#FDFDFD")
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        PRIMARY_COLOR, ACCENT_COLOR, BG_COLOR, TEXT_COLOR = "#005A9C", "#004B80", "#FDFDFD", "#1C1C1C"
        self.style.configure('.', background=BG_COLOR, foreground=TEXT_COLOR)
        self.style.configure('TFrame', background=BG_COLOR)
        self.style.configure('TLabel', font=('Calibri', 11), background=BG_COLOR)
        self.style.configure('Title.TLabel', font=('Calibri', 24, 'bold'))
        self.style.configure('Subtitle.TLabel', font=('Calibri', 14))
        self.style.configure('Content.TLabel', font=('Calibri', 12))
        self.style.configure('Accent.TButton', font=('Calibri', 13, 'bold'), padding=12, background=PRIMARY_COLOR, foreground='white')
        self.style.map('Accent.TButton', background=[('active', ACCENT_COLOR)])
        self.style.configure('Secondary.TButton', font=('Calibri', 11))
        self.container = ttk.Frame(self)
        self.container.pack(fill="both", expand=True)
        self.menu_frame, self.map_frame, self.info_frame = None, None, None
        self.show_menu()

    def show_menu(self):
        if self.map_frame: self.map_frame.destroy(); self.map_frame = None
        if self.info_frame: self.info_frame.destroy(); self.info_frame = None
        
        self.menu_frame = ttk.Frame(self.container, padding="40 40 40 40")
        
        ttk.Label(self.menu_frame, text="Sistema de Rutas y Análisis de Redes", style='Title.TLabel').pack(pady=(20, 10))
        
        route_frame = ttk.LabelFrame(self.menu_frame, text=" Búsqueda de Ruta Óptima ", padding="20 10")
        route_frame.pack(pady=15, fill='x', expand=True)
        ttk.Label(route_frame, text="Encuentra el camino más rápido desde tu ubicación a un punto seguro.").pack(pady=(0,15))
        ttk.Button(route_frame, text="🧭 Ruta con Dijkstra", style='Accent.TButton', command=lambda: self.abrir_mapa("dijkstra")).pack(pady=5, fill='x', ipady=5)
        ttk.Button(route_frame, text="⭐ Ruta con A-Star (A*)", style='Accent.TButton', command=lambda: self.abrir_mapa("astar")).pack(pady=5, fill='x', ipady=5)

        network_frame = ttk.LabelFrame(self.menu_frame, text=" Análisis de la Red de Evacuación ", padding="20 10")
        network_frame.pack(pady=15, fill='x', expand=True)
        ttk.Label(network_frame, text="Identifica las intersecciones más críticas (cuellos de botella) en el mapa.").pack(pady=(0,15))
        ttk.Button(network_frame, text="🚦 Identificar Cuellos de Botella (Centralidad)", style='Accent.TButton', command=lambda: self.abrir_mapa("centrality")).pack(pady=5, fill='x', ipady=5)
        
        ttk.Separator(self.menu_frame, orient='horizontal').pack(pady=30, fill='x')
        
        secondary_buttons_frame = ttk.Frame(self.menu_frame)
        secondary_buttons_frame.pack(pady=10)
        info_integrantes = "🧑‍💻 Integrantes del equipo:\n\nRenzo Gabriel Gutierrez Fernandez (u20231b830)\n\nValentino Sandoval Paiva (u20211a962)"
        
        info_proyecto = (
            "📘 Sobre el Proyecto:\n\n"
            "Este sistema utiliza un grafo de +9000 nodos y +20000 aristas para dos análisis principales:\n\n"
            "1. Búsqueda de Rutas (Dijkstra, A*): Calcula el camino más rápido a un punto seguro.\n"
            "2. Análisis de Puntos Críticos: Identifica los cuellos de botella de la red.\n\n"
            "El costo de cada calle se calcula con la fórmula:\n\n"
            "Costo = Tiempo_Base × Factor_Riesgo\n\n"
            "Donde:\n"
            "Tiempo_Base = (Distancia / Velocidad) × 60\n"
            "Factor_Riesgo = 1 + (Vulnerabilidad × 2)"
        )

        ttk.Button(secondary_buttons_frame, text="👥 Integrantes", style='Secondary.TButton', command=lambda: self.show_info_page("Integrantes", info_integrantes)).pack(side='left', padx=10)
        ttk.Button(secondary_buttons_frame, text="ℹ️ Sobre el Proyecto", style='Secondary.TButton', command=lambda: self.show_info_page("Sobre el Proyecto", info_proyecto, 'left')).pack(side='left', padx=10)
        ttk.Button(secondary_buttons_frame, text="❌ Salir", style='Secondary.TButton', command=self.destroy).pack(side='left', padx=10)
        
        self.menu_frame.pack(fill="both", expand=True)

    def abrir_mapa(self, algorithm_choice: str):
        if self.menu_frame: self.menu_frame.pack_forget()
        self.map_frame = MapViewFrame(self.container, app_controller=self, algorithm_choice=algorithm_choice)
        self.map_frame.pack(fill="both", expand=True)

    def show_info_page(self, title, content, text_align='center'):
        if self.menu_frame: self.menu_frame.pack_forget()
        self.info_frame = ttk.Frame(self.container)
        self.info_frame.pack(fill="both", expand=True)
        center_frame = ttk.Frame(self.info_frame)
        center_frame.place(relx=0.5, rely=0.5, anchor='center', relwidth=0.8)
        ttk.Label(center_frame, text=title, style='Title.TLabel', justify='center').pack(pady=(0, 20))
        content_label = ttk.Label(center_frame, text=content, style='Content.TLabel', justify=text_align)
        content_label.pack(pady=15)
        content_label.bind('<Configure>', lambda e: content_label.config(wraplength=e.width))
        ttk.Button(center_frame, text="◄ Volver al Menú", style='Accent.TButton', command=self.show_menu).pack(pady=30)

if __name__ == "__main__":
    app = App()
    app.mainloop()

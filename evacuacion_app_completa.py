import tkinter
from tkinter import ttk
import tkintermapview
import pandas as pd
import networkx as nx
from scipy.spatial import KDTree
import os
import threading
from queue import Queue, Empty
import math
import geojson

class MapViewFrame(tkinter.Frame):
    def __init__(self, master, app_controller, algorithm_choice: str):
        super().__init__(master)
        self.app = app_controller
        self.algorithm_choice = algorithm_choice
        self.algorithm_info = {
            "dijkstra": {"name": "Dijkstra", "color": "#E63946"},
            "astar": {"name": "A*", "color": "#588157"},
            "bellman-ford": {"name": "Bellman-Ford", "color": "#FFC300"}
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
        self.G, self.pos_nodos, self.kd_tree_nodos, self.df_nodos = None, None, None, None
        self.puntos_seguros_data = []
        self.puntos_seguros_markers = {}
        self.origen_marker, self.destino_marker, self.ruta_path = None, None, None
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
        distritos_de_interes = [
            "SAN ISIDRO", "MIRAFLORES", "SURQUILLO", 
            "SAN BORJA", "BARRANCO", "SANTIAGO DE SURCO"
        ]
        geojson_path = "peru_distrital_simple.geojson"
        DISTRITO_PROPERTY_KEY = 'NOMBDIST'
        PROVINCIA_PROPERTY_KEY = 'NOMBPROV'

        if not os.path.exists(geojson_path):
            self.set_status_text(f"Advertencia: No se encontró '{geojson_path}'. No se mostrarán los límites.")
            return

        try:
            with open(geojson_path, "r", encoding="utf-8") as f:
                geojson_data = geojson.load(f)
        except Exception as e:
            self.set_status_text("Error fatal: No se pudo leer el archivo de límites.")
            return

        for feature in geojson_data['features']:
            try:
                properties = feature.get('properties', {})
                provincia_nombre = properties.get(PROVINCIA_PROPERTY_KEY, '').upper()
                
                if provincia_nombre == 'LIMA':
                    distrito_nombre = properties.get(DISTRITO_PROPERTY_KEY, '').upper()
                    if distrito_nombre in distritos_de_interes:
                        geometria = feature.get('geometry')
                        if not geometria: continue

                        if geometria['type'] == 'Polygon':
                            geometries = [geometria['coordinates']]
                        elif geometria['type'] == 'MultiPolygon':
                            geometries = geometria['coordinates']
                        else:
                            continue
                        
                        for geometry_coords in geometries:
                            coordenadas_exteriores = geometry_coords[0]
                            if len(coordenadas_exteriores) < 2: continue
                            
                            coordenadas_corregidas = [(coord[1], coord[0]) for coord in coordenadas_exteriores]
                            
                            self.map_widget.set_path(coordenadas_corregidas,
                                                     color="#0004FF",
                                                     width=1)
            except Exception as e:
                dist_problematico = feature.get('properties', {}).get(DISTRITO_PROPERTY_KEY, 'DESCONOCIDO')

    def cargar_datos_iniciales(self):
        try:
            nodos_path = "nodos_lima.csv"
            aristas_path = "calles_lima_con_vulnerabilidad.csv"
            puntos_path = "puntos_seguros.csv"
            df_nodos_full = pd.read_csv(nodos_path)
            df_nodos_full['lat'] = pd.to_numeric(df_nodos_full['lat'], errors='coerce')
            df_nodos_full['lon'] = pd.to_numeric(df_nodos_full['lon'], errors='coerce')
            df_nodos_full.dropna(subset=['lat', 'lon'], inplace=True)
            df_aristas = pd.read_csv(aristas_path)
            df_puntos_seguros = pd.read_csv(puntos_path)
            G_full = nx.DiGraph()
            G_full.add_nodes_from(df_nodos_full['id'])
            for _, arista in df_aristas.iterrows():
                velocidad_kmh = arista.get('velocidad_max', 30)
                if not isinstance(velocidad_kmh, (int, float)) or velocidad_kmh <= 0:
                    velocidad_kmh = 30
                distancia_km = arista['longitud'] / 1000
                tiempo_en_minutos = (distancia_km / velocidad_kmh) * 60
                penalizacion_riesgo = 1 + (arista.get('vulnerabilidad', 0) * 2.0)
                peso = tiempo_en_minutos * penalizacion_riesgo
                G_full.add_edge(arista['origen'], arista['destino'], weight=peso)
                if not arista.get('sentido_unico', False):
                    G_full.add_edge(arista['destino'], arista['origen'], weight=peso)
            
            main_component_nodes = max(nx.weakly_connected_components(G_full), key=len)
            self.G = G_full.subgraph(main_component_nodes).copy()
            self.df_nodos = df_nodos_full[df_nodos_full['id'].isin(main_component_nodes)]
            
            if self.df_nodos.empty:
                self.gui_queue.put((self.set_status_text, ("Error: Los datos de nodos no son válidos.",))); return
            try:
                self.kd_tree_nodos = KDTree(self.df_nodos[['lat', 'lon']].values)
            except Exception as e:
                self.gui_queue.put((self.set_status_text, (f"Error fatal con los datos de nodos: {e}",))); return

            self.pos_nodos = {n['id']: (n['lat'], n['lon']) for _, n in self.df_nodos.iterrows()}
            self.puntos_seguros_data = [p.to_dict() for _, p in df_puntos_seguros.iterrows() if self.encontrar_nodo_cercano(p["lat"], p["lon"]) in self.G]
            
            def setup_map():
                self.dibujar_limites_distritales_geojson()
                for punto in self.puntos_seguros_data:
                    marker = self.map_widget.set_marker(punto["lat"], punto["lon"], text=punto["nombre"], text_color="#2E603A", marker_color_circle="#588157", marker_color_outside="#2E603A")
                    self.puntos_seguros_markers[(punto["lat"], punto["lon"])] = marker
                
                self.map_widget.set_position(-12.119, -77.021)
                self.map_widget.set_zoom(14)
                self.map_widget.add_left_click_map_command(self.on_map_click)
                algo_name = self.algorithm_info[self.algorithm_choice]["name"]
                self.set_status_text(f"Algoritmo: {algo_name}. Haz clic para elegir tu ubicación.")
            self.gui_queue.put((setup_map, ()))
        except Exception as e: self.gui_queue.put((self.set_status_text, (f"Error fatal al cargar datos: {e}",)))

    def set_status_text(self, text): self.status_label.config(text=text)

    def on_map_click(self, coords):
        if self.ruta_path: self.ruta_path.delete()
        if self.origen_marker: self.origen_marker.delete()
        
        if self.last_destination_info:
            if self.destino_marker: self.destino_marker.delete()
            p = self.last_destination_info
            marker = self.map_widget.set_marker(p["lat"], p["lon"], text=p["nombre"], text_color="#2E603A", marker_color_circle="#588157", marker_color_outside="#2E603A")
            self.puntos_seguros_markers[(p["lat"], p["lon"])] = marker
            self.last_destination_info = None

        self.origen_marker = self.map_widget.set_marker(coords[0], coords[1], text="Tu Ubicación")
        algo_name = self.algorithm_info[self.algorithm_choice]["name"]
        self.set_status_text(f"Calculando ruta con {algo_name} desde ({coords[0]:.4f}, {coords[1]:.4f})...")
        
        threading.Thread(target=self.encontrar_y_dibujar_ruta, args=(coords[0], coords[1]), daemon=True).start()
        
    def encontrar_nodo_cercano(self, lat, lon):
        _, indice = self.kd_tree_nodos.query([lat, lon])
        return self.df_nodos.iloc[indice]['id']
    
    def astar_heuristic(self, u, v):
        pos_u = self.pos_nodos[u]
        pos_v = self.pos_nodos[v]
        return math.sqrt((pos_u[0] - pos_v[0])**2 + (pos_u[1] - pos_v[1])**2)

    def encontrar_y_dibujar_ruta(self, origen_lat, origen_lon):
        if self.G is None: return
        try:
            nodo_origen = self.encontrar_nodo_cercano(origen_lat, origen_lon)
            mejor_tiempo, mejor_destino_info = float('inf'), None
            for punto in self.puntos_seguros_data:
                try:
                    nodo_destino = self.encontrar_nodo_cercano(punto["lat"], punto["lon"])
                    if nodo_origen == nodo_destino: continue
                    tiempo = nx.dijkstra_path_length(self.G, source=nodo_origen, target=nodo_destino, weight='weight')
                    if tiempo < mejor_tiempo: mejor_tiempo, mejor_destino_info = tiempo, punto
                except (nx.NetworkXNoPath, nx.NodeNotFound): continue
            
            if mejor_destino_info is None:
                self.gui_queue.put((self.set_status_text, ("No se encontró ruta a ningún punto seguro.",))); return

            final_nodo_destino = self.encontrar_nodo_cercano(mejor_destino_info["lat"], mejor_destino_info["lon"])
            ruta_nodos = None
            if self.algorithm_choice == "dijkstra": ruta_nodos = nx.dijkstra_path(self.G, source=nodo_origen, target=final_nodo_destino, weight='weight')
            elif self.algorithm_choice == "astar": ruta_nodos = nx.astar_path(self.G, source=nodo_origen, target=final_nodo_destino, heuristic=self.astar_heuristic, weight='weight')
            elif self.algorithm_choice == "bellman-ford": ruta_nodos = nx.bellman_ford_path(self.G, source=nodo_origen, target=final_nodo_destino, weight='weight')
            if not ruta_nodos: raise ValueError("El algoritmo no devolvió ninguna ruta.")
            path_coords = [self.pos_nodos[nodo] for nodo in ruta_nodos]
            
            def draw_on_gui():
                if len(path_coords) > 1:
                    info = self.algorithm_info[self.algorithm_choice]
                    self.ruta_path = self.map_widget.set_path(path_coords, color=info["color"], width=5)
                    dest_coords = (mejor_destino_info["lat"], mejor_destino_info["lon"])
                    if dest_coords in self.puntos_seguros_markers:
                        self.puntos_seguros_markers[dest_coords].delete()
                        del self.puntos_seguros_markers[dest_coords]
                    self.destino_marker = self.map_widget.set_marker(mejor_destino_info["lat"], mejor_destino_info["lon"], text=f"Destino: {mejor_destino_info['nombre']}", text_color="#A4161A", marker_color_circle="#E63946", marker_color_outside="#A4161A")
                    self.last_destination_info = mejor_destino_info
                    self.set_status_text(f"Ruta a {mejor_destino_info['nombre']} encontrada. Tiempo estimado: {mejor_tiempo:.2f} min.")
                else:
                    self.set_status_text("Error: la ruta calculada es demasiado corta para dibujarse.")
            self.gui_queue.put((draw_on_gui, ()))
        except Exception as e: self.gui_queue.put((self.set_status_text, (f"Error al calcular la ruta: {e}",)))

class App(tkinter.Tk):
    def __init__(self):
        super().__init__()
        self.title("Sistema de Rutas de Evacuación - Distritos Seleccionados")
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
        ttk.Label(self.menu_frame, text="Sistema de Rutas de Evacuación", style='Title.TLabel').pack(pady=(20, 30))
        ttk.Label(self.menu_frame, text="Seleccione un algoritmo para el cálculo de la ruta:", style='Subtitle.TLabel').pack(pady=15)
        ttk.Button(self.menu_frame, text="🧭 Ruta con Dijkstra", style='Accent.TButton', command=lambda: self.abrir_mapa("dijkstra")).pack(pady=8, fill='x', expand=True, ipady=5)
        ttk.Button(self.menu_frame, text="⭐ Ruta con A-Star (A*)", style='Accent.TButton', command=lambda: self.abrir_mapa("astar")).pack(pady=8, fill='x', expand=True, ipady=5)
        ttk.Button(self.menu_frame, text="🔔 Ruta con Bellman-Ford", style='Accent.TButton', command=lambda: self.abrir_mapa("bellman-ford")).pack(pady=8, fill='x', expand=True, ipady=5)
        ttk.Separator(self.menu_frame, orient='horizontal').pack(pady=40, fill='x')
        secondary_buttons_frame = ttk.Frame(self.menu_frame)
        secondary_buttons_frame.pack(pady=10)
        info_integrantes = "🧑‍💻 Integrantes del equipo:\n\nRenzo Gabriel Gutierrez Fernandez (u20231b830)\n\nValentino Sandoval Paiva (u20211a962)"
        info_proyecto = "📘 Sobre el Proyecto:\n\nEste sistema calcula rutas de evacuación óptimas para los distritos de\nSan Isidro, Miraflores, Surquillo, San Borja, Barranco y Santiago de Surco.\n\nUtiliza un grafo de +9000 nodos y +20000 aristas, donde el 'costo' de cada calle\nse calcula combinando el tiempo de viaje en vehículo (según la velocidad máxima de la vía)\ncon una penalización basada en la vulnerabilidad sísmica de la zona."
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
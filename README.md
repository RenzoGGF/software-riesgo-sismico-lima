### Sistema de Rutas de Evacuación Sísmica para ciertos distritos de Lima, Perú
Este aplicativo permite calcular rutas óptimas hacia zonas seguras en caso de sismo en los distritos de **Miraflores, San Isidro, Surquillo, San Borja, Barranco y Santiago de Surco.**

**🔧 Características**

- Usa datos reales de OpenStreetMap y vulnerabilidad sísmica de CENEPRED e INEI.
- Modela la red vial de Lima como un grafo con más de 9000 nodos y 20000 aristas.
- Implementa algoritmos como Dijkstra, A* y Bellman-Ford para el cálculo de rutas, y la estructura de datos espacial KD-Tree para la geolocalización eficiente del usuario en el mapa.
- Incluye mapa interactivo para seleccionar tu ubicación y visualizar la ruta segura más eficiente.

**📦 Contenido del Release**

- software-riesgo-sismico-lima.exe: aplicación lista para usar en Windows.
- Todos los archivos CSV y GeoJSON necesarios ya están integrados.
- No requiere instalación de Python ni bibliotecas externas.

**📍 Modo de uso**

- Descarga y ejecuta el .exe.
- Haz clic en tu ubicación en el mapa.
- El sistema calculará y trazará la ruta más segura al punto seguro más cercano.

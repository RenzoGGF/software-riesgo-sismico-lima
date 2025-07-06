### Sistema de Rutas de Evacuación Sísmica para ciertos distritos de Lima, Perú
Este aplicativo permite calcular rutas óptimas hacia zonas seguras en caso de sismo en los distritos de **Miraflores, San Isidro, Surquillo, San Borja, Barranco y Santiago de Surco.**

**🔧 Características**

- Usa datos reales de OpenStreetMap y vulnerabilidad sísmica de fuentes como CENEPRED e INEI.
- Modela la red vial como un grafo dirigido con más de 9000 nodos y 20000 aristas.
- Implementa algoritmos como Dijkstra, A* y Centralidad de Intermediación para dos análisis: cálculo de rutas seguras y detección de puntos - críticos (cuellos de botella).
- Utiliza una estructura de datos espacial KD-Tree para la geolocalización eficiente del usuario en el mapa.
- Incluye un mapa interactivo para seleccionar tu ubicación y visualizar la ruta, o para observar los puntos críticos de la red.

**📦 Contenido del Release**

- evacuacion_app.exe: aplicación lista para usar en Windows.
- Todos los archivos CSV y GeoJSON necesarios ya están integrados.
- No requiere instalación de Python ni bibliotecas externas.

**📍 Modo de uso**

- Solo descarga y ejecuta el **.exe**.
- Haz clic en tu ubicación en el mapa.
- El sistema calculará y trazará la ruta más segura al punto seguro más cercano.

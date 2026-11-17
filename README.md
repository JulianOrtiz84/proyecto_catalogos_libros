# Integración y comparación de catálogos de libros

Proyecto académico en Python para consultar, extraer, preparar y explorar registros bibliográficos de dos fuentes públicas, y practicar consultas SQL con SQLite.

## Fuentes

- [Open Library Search API](https://openlibrary.org/dev/docs/api/search): consulta de registros en formato JSON.
- [Books to Scrape, categoría Fiction](https://books.toscrape.com/catalogue/category/books/fiction_10/index.html): extracción de registros desde páginas HTML.

Books to Scrape advierte que sus precios y calificaciones son aleatorios y no representan información real. En este proyecto se usan únicamente para practicar conversión de datos, estadística descriptiva y visualización.

## Archivos principales

- `analisis_catalogos.py`: consulta las fuentes, revisa y consolida los datos, genera estadísticas y gráficos, exporta un CSV y crea una base de datos SQLite.
- `requirements.txt`: dependencias externas de Python.
- `catalogo_libros_unificado.csv`: catálogo consolidado de la ejecución.
- `catalogo_libros.db`: base de datos SQLite.
- `grafico_registros_por_fuente.png` y `grafico_calificaciones_demo.png`: visualizaciones generadas por el script.

Los datos sintéticos de prueba se almacenan en una tabla SQLite separada y no se mezclan con el análisis del catálogo.

## Instalación y ejecución

Desde PowerShell, en la carpeta del proyecto:

```powershell
& ".\.venv\Scripts\python.exe" -m pip install -r requirements.txt
& ".\.venv\Scripts\python.exe" .\analisis_catalogos.py
```

El script vuelve a consultar las fuentes y genera los archivos de salida en la carpeta desde la que se ejecuta.
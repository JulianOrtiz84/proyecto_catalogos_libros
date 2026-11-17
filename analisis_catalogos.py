"""Integra dos catálogos de libros y practica análisis, SQLite y scraping.

Fuentes consultadas:
- Open Library Search API: https://openlibrary.org/dev/docs/api/search
- Books to Scrape (sitio de práctica): https://books.toscrape.com/

Nota: Books to Scrape indica que sus precios y calificaciones son aleatorios
y no tienen significado real. Se conservan solo como variables de práctica.
"""

import random
import re
import sqlite3
import unicodedata
from urllib.parse import urljoin

import matplotlib.pyplot as plt
import pandas as pd
import requests
from bs4 import BeautifulSoup


# La API devuelve los resultados como JSON. Limitamos la muestra a 50 libros
# y solicitamos solo los campos necesarios para reducir la respuesta.
OPEN_LIBRARY_URL = "https://openlibrary.org/search.json"
PARAMETROS_OPEN_LIBRARY = {
    "q": "subject:fiction",
    "limit": 50,
    "fields": "title,author_name,first_publish_year,subject,key",
}

# Books to Scrape es un sitio creado para practicar extracción de información.
BOOKS_TO_SCRAPE_URL = (
    "https://books.toscrape.com/catalogue/category/books/fiction_10/index.html"
)


def obtener_libros_open_library():
    """Consulta la API JSON y devuelve sus resultados como un DataFrame."""

    respuesta = requests.get(
        OPEN_LIBRARY_URL,
        params=PARAMETROS_OPEN_LIBRARY,
        timeout=30,
    )
    # Si la API responde con un error HTTP, raise_for_status detiene el proceso
    # e informa el código del error en lugar de continuar con datos incompletos.
    respuesta.raise_for_status()

    # La API organiza los libros dentro de la clave "docs" del objeto JSON.
    documentos = respuesta.json().get("docs", [])
    registros = []

    for libro in documentos:
        autores = libro.get("author_name", [])
        temas = libro.get("subject", [])

        # Algunas obras no tienen autor, año o temas informados; en ese caso
        # guardamos None para que pandas lo trate como un valor ausente.
        registros.append(
            {
                "titulo": libro.get("title"),
                "autor": ", ".join(autores[:3]) if autores else None,
                "anio_publicacion": libro.get("first_publish_year"),
                "temas": ", ".join(temas[:3]) if temas else None,
                "fuente": "Open Library",
            }
        )

    return pd.DataFrame(registros)


def obtener_libros_scrapeados():
    """Extrae títulos y campos de demostración de todas las páginas de ficción."""

    registros = []
    url_actual = BOOKS_TO_SCRAPE_URL

    # La categoría tiene varias páginas. El enlace "next" permite recorrerlas
    # sin codificar manualmente cuántas páginas existen.
    while url_actual:
        respuesta = requests.get(url_actual, timeout=30)
        respuesta.raise_for_status()

        # Detectar la codificación evita caracteres dañados, como el símbolo £.
        respuesta.encoding = respuesta.apparent_encoding
        pagina = BeautifulSoup(respuesta.text, "html.parser")

        for libro in pagina.select("article.product_pod"):
            enlace_titulo = libro.select_one("h3 a")
            elemento_precio = libro.select_one(".price_color")
            elemento_disponibilidad = libro.select_one(".availability")
            elemento_calificacion = libro.select_one("p.star-rating")

            # Validamos que existan los elementos antes de leerlos. Si el HTML
            # cambia, el registro incompleto se omite en vez de causar un error.
            if not all(
                [enlace_titulo, elemento_precio, elemento_disponibilidad,
                 elemento_calificacion]
            ):
                continue

            clases = elemento_calificacion.get("class", [])
            calificacion = next(
                (clase for clase in clases if clase != "star-rating"),
                None,
            )

            registros.append(
                {
                    "titulo": enlace_titulo.get("title"),
                    "precio_demo": elemento_precio.get_text(strip=True),
                    "disponibilidad": elemento_disponibilidad.get_text(
                        " ", strip=True
                    ),
                    "calificacion_demo": calificacion,
                    "categoria": "Fiction",
                    "fuente": "Books to Scrape",
                }
            )

        # Convertimos el enlace relativo de la siguiente página a una URL
        # completa. Si no existe, terminamos el recorrido.
        enlace_siguiente = pagina.select_one("li.next a")
        url_actual = (
            urljoin(url_actual, enlace_siguiente.get("href"))
            if enlace_siguiente
            else None
        )

    return pd.DataFrame(registros)


def normalizar_titulo(titulo):
    """Prepara un título para buscar coincidencias sin cambiar el original."""

    texto = unicodedata.normalize("NFKD", str(titulo))
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    return re.sub(r"\s+", " ", texto).strip().casefold()


def revisar_calidad(libros_api, libros_web):
    """Informa problemas de calidad detectables sin borrar datos en silencio."""

    for nombre, datos in [
        ("Open Library", libros_api),
        ("Books to Scrape", libros_web),
    ]:
        titulo_vacio = datos["titulo"].isna() | datos["titulo"].astype(str).str.strip().eq("")
        titulos_normalizados = datos.loc[~titulo_vacio, "titulo"].map(normalizar_titulo)
        duplicados = titulos_normalizados.duplicated().sum()

        print(f"\nREVISIÓN DE CALIDAD - {nombre}")
        print("Títulos vacíos:", int(titulo_vacio.sum()))
        print("Títulos repetidos dentro de la fuente:", int(duplicados))

        if nombre == "Books to Scrape":
            # La conversión aquí es solo para validar que el dato pueda leerse
            # como número; la transformación definitiva ocurre al consolidar.
            precios = pd.to_numeric(
                datos["precio_demo"].str.replace("£", "", regex=False),
                errors="coerce",
            )
            print("Precios que no se pudieron convertir:", int(precios.isna().sum()))

    # El cruce por título solo es defendible si hay coincidencias reales.
    titulos_api = set(libros_api["titulo"].dropna().map(normalizar_titulo))
    titulos_web = set(libros_web["titulo"].dropna().map(normalizar_titulo))
    coincidencias = sorted(titulos_api.intersection(titulos_web))
    print("\nCoincidencias de título entre fuentes:", len(coincidencias))
    if coincidencias:
        print("Ejemplos de títulos coincidentes:", coincidencias[:5])
    else:
        print("No se fuerza un cruce libro a libro: no hay títulos coincidentes.")


def consolidar_catalogos(libros_api, libros_web):
    """Normaliza campos, concatena registros y enriquece por fuente con merge."""

    api = libros_api.copy()
    web = libros_web.copy()

    # Excluimos únicamente registros sin título utilizable. No imputamos autor,
    # año ni temas ausentes porque las fuentes no siempre ofrecen esos campos.
    api = api.loc[
        api["titulo"].notna() & api["titulo"].astype(str).str.strip().ne("")
    ].copy()
    web = web.loc[
        web["titulo"].notna() & web["titulo"].astype(str).str.strip().ne("")
    ].copy()
    api["titulo"] = api["titulo"].astype(str).str.strip()
    web["titulo"] = web["titulo"].astype(str).str.strip()

    # El precio llega con el símbolo £ y como texto; quitamos el símbolo y
    # convertimos a número para habilitar estadísticas. El campo conserva la
    # palabra "demo" para advertir que no es un precio de mercado real.
    web["precio_gbp_demo"] = pd.to_numeric(
        web["precio_demo"].str.replace("£", "", regex=False),
        errors="coerce",
    )

    # Las estrellas están guardadas como palabras en el HTML. El diccionario
    # las traduce a escala ordinal de 1 a 5 para resumirlas y graficarlas.
    equivalencia_estrellas = {
        "One": 1,
        "Two": 2,
        "Three": 3,
        "Four": 4,
        "Five": 5,
    }
    web["calificacion_demo"] = web["calificacion_demo"].map(equivalencia_estrellas)
    web = web.drop(columns=["precio_demo"])

    columnas_catalogo = [
        "titulo", "autor", "anio_publicacion", "temas", "precio_gbp_demo",
        "disponibilidad", "calificacion_demo", "categoria", "fuente",
    ]

    # Reindexar asigna las mismas columnas a ambas fuentes; concat apila filas.
    # Los NaN resultantes son estructurales cuando la fuente no brinda ese campo.
    api = api.reindex(columns=columnas_catalogo)
    web = web.reindex(columns=columnas_catalogo)
    catalogo = pd.concat([api, web], ignore_index=True)

    # DataFrame auxiliar que describe cómo se obtuvo cada fuente. Este cruce es
    # válido porque "fuente" es una clave compartida y única en la tabla auxiliar.
    metadata_fuentes = pd.DataFrame(
        [
            {
                "fuente": "Open Library",
                "formato_origen": "JSON",
                "metodo_acceso": "API de búsqueda",
            },
            {
                "fuente": "Books to Scrape",
                "formato_origen": "HTML",
                "metodo_acceso": "Web scraping",
            },
        ]
    )
    catalogo = catalogo.merge(
        metadata_fuentes,
        on="fuente",
        how="left",
        validate="many_to_one",
    )

    return catalogo


def analizar_catalogo(catalogo):
    """Imprime resúmenes y crea visualizaciones exploratorias en PNG."""

    print("\nANÁLISIS EXPLORATORIO")
    print("\nRegistros por fuente:")
    print(catalogo["fuente"].value_counts())

    print("\nValores vacíos por columna:")
    print(catalogo.isna().sum())

    # Separamos la fuente web para no mezclar variables que no existen en
    # Open Library. Las estadísticas son descriptivas de esta muestra de práctica.
    datos_demo = catalogo.loc[
        catalogo["fuente"] == "Books to Scrape",
        ["precio_gbp_demo", "calificacion_demo"],
    ]
    print("\nResumen de precio y calificación de demostración:")
    print(datos_demo.describe().round(2))

    # Gráfico de barras que compara el número de registros obtenidos por fuente.
    conteo_fuentes = catalogo["fuente"].value_counts()
    ax = conteo_fuentes.plot(kind="bar", color=["#4472C4", "#70AD47"])
    ax.set_title("Registros obtenidos por fuente")
    ax.set_xlabel("Fuente")
    ax.set_ylabel("Cantidad de registros")
    ax.tick_params(axis="x", rotation=0)
    plt.tight_layout()
    plt.savefig("grafico_registros_por_fuente.png", dpi=150)
    plt.close()

    # El segundo gráfico muestra frecuencias de calificaciones ficticias de demo.
    conteo_calificaciones = datos_demo["calificacion_demo"].value_counts().sort_index()
    ax = conteo_calificaciones.plot(kind="bar", color="#ED7D31")
    ax.set_title("Calificaciones de demostración en Books to Scrape")
    ax.set_xlabel("Calificación (estrellas)")
    ax.set_ylabel("Cantidad de libros")
    ax.tick_params(axis="x", rotation=0)
    plt.tight_layout()
    plt.savefig("grafico_calificaciones_demo.png", dpi=150)
    plt.close()

    print("\nGráficos guardados:")
    print("- grafico_registros_por_fuente.png")
    print("- grafico_calificaciones_demo.png")


def generar_datos_sinteticos(semilla=2026, cantidad=3):
    """Genera libros ficticios reproducibles para practicar INSERT y UPDATE."""

    generador = random.Random(semilla)
    registros = []
    for numero in range(1, cantidad + 1):
        registros.append(
            {
                "titulo": f"Libro sintético de prueba {numero}",
                "autor": f"Autor ficticio {numero}",
                "precio_demo": round(generador.uniform(10, 60), 2),
                "calificacion_demo": generador.randint(1, 5),
                "fuente": "Prueba sintética",
            }
        )
    return pd.DataFrame(registros)


def ejecutar_consultas_sql(catalogo):
    """Guarda el catálogo y ejecuta consultas SQL de lectura e inserción/actualización."""

    nombre_base = "catalogo_libros.db"
    conexion = sqlite3.connect(nombre_base)

    try:
        # pandas escribe los registros del catálogo en la tabla libros.
        catalogo.to_sql("libros", conexion, if_exists="replace", index=False)

        consultas = {
            "COUNT(*)": "SELECT COUNT(*) AS total_registros FROM libros;",
            "COUNT(DISTINCT titulo)": (
                "SELECT COUNT(DISTINCT titulo) AS titulos_distintos FROM libros;"
            ),
            "Conteo por fuente": (
                "SELECT fuente, COUNT(*) AS cantidad FROM libros "
                "GROUP BY fuente ORDER BY fuente;"
            ),
        }

        print("\nCONSULTAS SQL EN SQLITE")
        for etiqueta, consulta in consultas.items():
            print(f"\n{etiqueta}:")
            print(pd.read_sql_query(consulta, conexion))

        # Los signos ? son parámetros: SQLite recibe los valores por separado,
        # evitando construir la consulta con texto concatenado.
        consulta_igual = (
            "SELECT titulo, autor, anio_publicacion FROM libros "
            "WHERE fuente = ? LIMIT 5;"
        )
        print("\nWHERE fuente = 'Open Library':")
        print(
            pd.read_sql_query(
                consulta_igual,
                conexion,
                params=("Open Library",),
            )
        )

        consulta_in = (
            "SELECT titulo, autor, fuente FROM libros WHERE autor IN (?, ?);"
        )
        print("\nWHERE autor IN ('Mary Shelley', 'Oscar Wilde'):")
        print(
            pd.read_sql_query(
                consulta_in,
                conexion,
                params=("Mary Shelley", "Oscar Wilde"),
            )
        )

        # Tabla de práctica separada: los datos sintéticos nunca se mezclan con
        # el catálogo de fuentes públicas ni con sus estadísticas o gráficos.
        pruebas = generar_datos_sinteticos()
        cursor = conexion.cursor()
        cursor.execute("DROP TABLE IF EXISTS libros_prueba_sinteticos;")
        cursor.execute(
            """CREATE TABLE libros_prueba_sinteticos (
                id INTEGER PRIMARY KEY,
                titulo TEXT NOT NULL,
                autor TEXT NOT NULL,
                precio_demo REAL,
                calificacion_demo INTEGER,
                fuente TEXT NOT NULL
            );"""
        )

        # INSERT agrega cada fila ficticia a la tabla de prueba.
        cursor.executemany(
            """INSERT INTO libros_prueba_sinteticos
               (titulo, autor, precio_demo, calificacion_demo, fuente)
               VALUES (?, ?, ?, ?, ?);""",
            list(pruebas.itertuples(index=False, name=None)),
        )

        # UPDATE modifica un registro de prueba sin tocar la tabla principal.
        cursor.execute(
            "UPDATE libros_prueba_sinteticos SET calificacion_demo = ? WHERE id = ?;",
            (5, 1),
        )
        conexion.commit()

        print("\nDatos sintéticos tras INSERT y UPDATE (tabla de prueba):")
        print(
            pd.read_sql_query(
                "SELECT * FROM libros_prueba_sinteticos ORDER BY id;",
                conexion,
            )
        )
    finally:
        conexion.close()

    print("\nBase de datos SQLite guardada:", nombre_base)


def main():
    """Ejecuta las etapas de adquisición, calidad, análisis y persistencia."""

    libros_api = obtener_libros_open_library()
    libros_web = obtener_libros_scrapeados()

    print("OPEN LIBRARY - JSON")
    print("Cantidad de registros:", len(libros_api))
    print("Columnas:", list(libros_api.columns))
    print(libros_api.head())

    print("\nBOOKS TO SCRAPE - HTML")
    print("Cantidad de registros:", len(libros_web))
    print("Columnas:", list(libros_web.columns))
    print(libros_web.head())

    # Revisamos títulos vacíos, repeticiones y posibles cruces antes de unir.
    revisar_calidad(libros_api, libros_web)

    catalogo = consolidar_catalogos(libros_api, libros_web)
    print("\nCATÁLOGO CONSOLIDADO")
    print("Filas y columnas:", catalogo.shape)
    print("\nValores vacíos por columna:")
    print(catalogo.isna().sum())
    print("\nPrimeros cinco registros:")
    print(catalogo.head())

    # utf-8-sig permite que Excel reconozca correctamente tildes y caracteres.
    nombre_csv = "catalogo_libros_unificado.csv"
    catalogo.to_csv(nombre_csv, index=False, encoding="utf-8-sig")
    print("\nArchivo CSV guardado:", nombre_csv)

    analizar_catalogo(catalogo)
    ejecutar_consultas_sql(catalogo)


if __name__ == "__main__":
    main()

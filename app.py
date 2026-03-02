import streamlit as st
import fitz  # PyMuPDF
import pandas as pd
import json
import time
import base64
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from io import BytesIO

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Procesador de Encuestas", layout="wide")

st.title("📄 Extractor de Datos de Encuestas (PDF a Excel)")
st.markdown("Sube tus PDFs. El sistema procesará una página cada 6 segundos para respetar los límites gratuitos.")

# --- BARRA LATERAL PARA LA API KEY ---
with st.sidebar:
    st.header("Configuración")
    api_key = st.text_input("Ingresa tu Google API Key:", type="password")
    st.markdown("[Consigue tu API Key aquí](https://aistudio.google.com/app/apikey)")

if not api_key:
    st.warning("👈 Por favor, ingresa tu API Key en la barra lateral para comenzar.")
    st.stop()

# Inicializar el modelo
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0,
    google_api_key=api_key,
    max_retries=2
)

# --- MEMORIA DE LA APLICACIÓN (STATE) ---
# Esto evita que los datos se borren al interactuar con los botones
if 'resultados' not in st.session_state:
    st.session_state.resultados = []
if 'detener' not in st.session_state:
    st.session_state.detener = False

# --- FUNCIONES ---
def pdf_pagina_a_imagen(pagina_pdf):
    pix = pagina_pdf.get_pixmap(dpi=150)
    img_data = pix.tobytes("png")
    return base64.b64encode(img_data).decode("utf-8")

def analizar_pagina(imagen_b64, numero_pagina, nombre_archivo):
    prompt_sistema = """
    Actúa como un digitador de datos. Estás transcribiendo una 'Encuesta de Salida - Kuraq Ñañayki'.
    La imagen corresponde a UNA estudiante. Extrae los datos manuscritos o marcados.
    
    Devuelve un JSON estricto con estas claves (si no hay dato, pon null):
    1. "nombres_apellidos": (Texto manuscrito pregunta 1)
    2. "genero": (Femenino/Masculino pregunta 2)
    3. "grado": (3ro/4to/5to pregunta 3)
    4. "seccion": (Texto pregunta 4)
    5. "carrera_interes_antes": (Texto pregunta 5)
    6. "taller_volcanes_calificacion": (Numero 1-5 en tabla pregunta 6)
    7. "taller_minerales_calificacion": (Numero 1-5 en tabla pregunta 6)
    8. "taller_purificación_del_agua_calificacion": (Numero 1-5 en tabla pregunta 6)
    9. "taller_holograma_calificacion": (Numero 1-5 en tabla pregunta 6)
    10. "taller_introduccion_python_calificacion": (Numero 1-5 en tabla pregunta 6)
    11. "interes_stem_ahora": (Si/No/No sé pregunta 7)
    12. "volver a participar": (Si/No/No sé pregunta 8)
    13. "carreras_cree_para_mujeres": (Lista de carreras marcadas en preg 9 ej: ['Ingeniería', 'Ciencias'])
    14. "recomienda_programa_nps": (En la pregunta 10, identifica qué número del 0 al 10 tiene una 'X', un aspa, o está encerrado/marcado. ADVERTENCIA: La marca o 'X' puede cubrir fuertemente el número, fíjate en el que está exactamente debajo del tachón. Devuelve SOLO el número exacto en formato entero, ej: 8)
    15. "comentarios_mejora": (Texto manuscrito preg 11)
    16. "contacto": (Telefono/Email preg 12)
    """
    mensaje = HumanMessage(
        content=[
            {"type": "text", "text": prompt_sistema},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{imagen_b64}"}}
        ]
    )

    try:
        respuesta = llm.invoke([mensaje])
        texto_limpio = respuesta.content.replace("```json", "").replace("```", "").strip()
        datos = json.loads(texto_limpio)
        datos["origen_archivo"] = nombre_archivo
        datos["pagina_numero"] = numero_pagina + 1
        return datos
    except Exception as e:
        return {"error": str(e), "origen_archivo": nombre_archivo, "pagina_numero": numero_pagina + 1}

# --- INTERFAZ DE USUARIO ---
archivos_subidos = st.file_uploader("Selecciona los PDFs de las encuestas", type="pdf", accept_multiple_files=True)

# Controles de botones en columnas
col1, col2 = st.columns(2)
with col1:
    iniciar = st.button("🚀 Iniciar Procesamiento", use_container_width=True)
with col2:
    detener = st.button("🛑 Detener Proceso", use_container_width=True)

if detener:
    st.session_state.detener = True
    st.warning("⚠️ Procesamiento detenido. Puedes descargar los resultados extraídos hasta ahora.")

if iniciar:
    st.session_state.detener = False
    st.session_state.resultados = []  # Limpiar memoria al iniciar de nuevo
    
    progreso_texto = st.empty()
    barra_progreso = st.progress(0)
    tabla_resultados = st.empty()
    
    total_archivos = len(archivos_subidos)
    
    for idx_archivo, archivo in enumerate(archivos_subidos):
        if st.session_state.detener: break # Salir si se presionó detener
            
        doc = fitz.open("pdf", archivo.read())
        total_paginas = len(doc)
        
        for i in range(total_paginas):
            if st.session_state.detener: break # Salir si se presionó detener
                
            progreso_texto.text(f"Procesando: {archivo.name} | Página {i + 1} de {total_paginas} ...")
            
            pagina = doc.load_page(i)
            imagen = pdf_pagina_a_imagen(pagina)
            datos_estudiante = analizar_pagina(imagen, i, archivo.name)
            
            if datos_estudiante and "error" not in datos_estudiante:
                st.session_state.resultados.append(datos_estudiante)
                # Actualizar tabla visual
                tabla_resultados.dataframe(pd.DataFrame(st.session_state.resultados))
            elif "error" in datos_estudiante:
                st.error(f"Error en {archivo.name} - Página {i+1}: {datos_estudiante['error']}")
            
            # Pausa para la API gratuita
            time.sleep(6) 
        
        doc.close()
        
        if not st.session_state.detener:
            barra_progreso.progress((idx_archivo + 1) / total_archivos)

    if not st.session_state.detener:
        st.success("✅ ¡Procesamiento completado con éxito!")

# --- BOTÓN DE DESCARGA ---
# Siempre visible si hay datos en la memoria, sin importar si terminó o se detuvo
if len(st.session_state.resultados) > 0:
    st.markdown("---")
    st.subheader(f"📊 Datos listos para descargar ({len(st.session_state.resultados)} registros)")
    
    df_final = pd.DataFrame(st.session_state.resultados)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Encuestas')
    
    st.download_button(
        label="📥 Descargar Base de Datos en Excel",
        data=output.getvalue(),
        file_name="Base_Datos_WIM.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"

    )

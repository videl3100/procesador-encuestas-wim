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
st.set_page_config(page_title="Procesador de Encuestas KÑ 2026", layout="wide")

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
    # --- PROMPT ACTUALIZADO VERSIÓN 2026 ---
    prompt_sistema = """
    Actúa como un digitador de datos. Estás transcribiendo la 'Encuesta de Salida Versión 2026 KÑ' (Kuraq Ñañayki).
    La imagen corresponde a UNA estudiante. Extrae los datos manuscritos o marcados.
    
    Devuelve un JSON estricto con estas claves (si no hay dato, pon null):
    1. "colegio": (Texto manuscrito en el campo superior 'Colegio')
    2. "nombres_apellidos": (Texto manuscrito pregunta 1)
    3. "genero": (Femenino/Masculino marcado en pregunta 2)
    4. "grado": (3ro/4to/5to marcado en pregunta 3)
    5. "carrera_pensaba_estudiar_antes": (Texto manuscrito pregunta 4)
    6. "carrera_motivada_ahora": (Texto manuscrito pregunta 5)
    7. "taller_volcanes_gusto": (Numero del 1 al 5 en tabla pregunta 6)
    8. "taller_minerales_gusto": (Numero del 1 al 5 en tabla pregunta 6)
    9. "taller_elevador_hidraulico_gusto": (Numero del 1 al 5 en tabla pregunta 6)
    10. "taller_holograma_gusto": (Numero del 1 al 5 en tabla pregunta 6)
    11. "taller_ia_vision_gusto": (Numero del 1 al 5 en tabla pregunta 6)
    12. "facilidad_entender_temas": (Numero marcado del 1 al 5 en la pregunta 7)
    13. "volver_a_participar": (Sí/No/No sé marcado en pregunta 8)
    14. "carreras_cree_para_mujeres": (Lista de carreras marcadas en pregunta 9, ej: ['Ingeniería', 'Medicina'])
    15. "aporte_desarrollo": (Nada/Poco/Algo/Bastante/Mucho marcado en pregunta 10)
    16. "recomienda_programa_nps": (En la pregunta 11, identifica qué número del 0 al 10 tiene una 'X', un aspa, o está encerrado/marcado. ADVERTENCIA: La marca o 'X' puede cubrir fuertemente el número, fíjate en el que está debajo del tachón. Devuelve SOLO el número exacto, ej: 8)
    17. "comentarios_mejora": (Texto manuscrito pregunta 12)
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
    st.session_state.resultados = []  
    
    progreso_texto = st.empty()
    barra_progreso = st.progress(0)
    tabla_resultados = st.empty()
    
    total_archivos = len(archivos_subidos)
    
    for idx_archivo, archivo in enumerate(archivos_subidos):
        if st.session_state.detener: break 
            
        doc = fitz.open("pdf", archivo.read())
        total_paginas = len(doc)
        
        for i in range(total_paginas):
            if st.session_state.detener: break 
                
            progreso_texto.text(f"Procesando: {archivo.name} | Página {i + 1} de {total_paginas} ...")
            
            pagina = doc.load_page(i)
            imagen = pdf_pagina_a_imagen(pagina)
            datos_estudiante = analizar_pagina(imagen, i, archivo.name)
            
            if datos_estudiante and "error" not in datos_estudiante:
                st.session_state.resultados.append(datos_estudiante)
                tabla_resultados.dataframe(pd.DataFrame(st.session_state.resultados))
            elif "error" in datos_estudiante:
                st.error(f"Error en {archivo.name} - Página {i+1}: {datos_estudiante['error']}")
            
            time.sleep(6) 
        
        doc.close()
        
        if not st.session_state.detener:
            barra_progreso.progress((idx_archivo + 1) / total_archivos)

    if not st.session_state.detener:
        st.success("✅ ¡Procesamiento completado con éxito!")

# --- BOTÓN DE DESCARGA ---
if len(st.session_state.resultados) > 0:
    st.markdown("---")
    st.subheader(f"📊 Datos listos para descargar ({len(st.session_state.resultados)} registros)")
    
    df_final = pd.DataFrame(st.session_state.resultados)
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df_final.to_excel(writer, index=False, sheet_name='Encuestas_2026')
    
    st.download_button(
        label="📥 Descargar Base de Datos en Excel",
        data=output.getvalue(),
        file_name="Base_Datos_WIM_2026.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary"
    )

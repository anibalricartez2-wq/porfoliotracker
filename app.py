import streamlit as st
import sqlite3
import yfinance as yf
import math
import hashlib
import smtplib
from email.mime.text import MIMEText

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Gestor de Cartera", page_icon="📈", layout="wide")

# --- CONEXIÓN A BASE DE DATOS ---
conn = sqlite3.connect("cartera.db", check_same_thread=False)
c = conn.cursor()

def inicializar_db():
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE, password TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS posiciones
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, especie TEXT, 
                  cantidad INTEGER, inversion REAL, ganancia_obj REAL)''')
    conn.commit()

inicializar_db()

# --- FUNCIONES AUXILIARES ---
def hash_password(password):
    return hashlib.sha256(str.encode(password)).hexdigest()

def agregar_usuario(username, password):
    try:
        c.execute("INSERT INTO usuarios (username, password) VALUES (?, ?)", (username, hash_password(password)))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False

def login_usuario(username, password):
    c.execute("SELECT id FROM usuarios WHERE username=? AND password=?", (username, hash_password(password)))
    return c.fetchone()

def agregar_posicion(user_id, especie, cantidad, inversion, ganancia_obj):
    c.execute("INSERT INTO posiciones (user_id, especie, cantidad, inversion, ganancia_obj) VALUES (?, ?, ?, ?, ?)",
              (user_id, especie.upper(), cantidad, inversion, ganancia_obj))
    conn.commit()

def obtener_posiciones(user_id):
    c.execute("SELECT id, especie, cantidad, inversion, ganancia_obj FROM posiciones WHERE user_id=?", (user_id,))
    return c.fetchall()

def eliminar_posicion(pos_id):
    c.execute("DELETE FROM posiciones WHERE id=?", (pos_id,))
    conn.commit()

def enviar_alerta(email_dest, password_app, especie, nominales, precio_actual, monto_ganancia):
    remitente = email_dest # Asumimos que te lo enviás a vos mismo desde tu cuenta
    mensaje = MIMEText(f"¡Alerta de Take Profit!\n\nEspecie: {especie}\nPrecio Actual: ${precio_actual:.2f}\n"
                       f"Acción recomendada: Vender {nominales} nominales.\n"
                       f"Ganancia asegurada aproximada: ${monto_ganancia:.2f}.")
    mensaje['Subject'] = f"📈 ALERTA DE VENTA: {especie}"
    mensaje['From'] = remitente
    mensaje['To'] = remitente

    try:
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(remitente, password_app)
        server.sendmail(remitente, remitente, mensaje.as_string())
        server.quit()
        return True
    except Exception as e:
        return str(e)

# --- MANEJO DE SESIÓN ---
if "user_id" not in st.session_state:
    st.session_state["user_id"] = None
if "username" not in st.session_state:
    st.session_state["username"] = None

# --- SIDEBAR: LOGIN Y REGISTRO ---
st.sidebar.title("🔐 Acceso")
menu = st.sidebar.radio("Opciones", ["Iniciar Sesión", "Registrarse"])

if st.session_state["user_id"] is None:
    if menu == "Registrarse":
        st.sidebar.subheader("Crear Cuenta nueva")
        new_user = st.sidebar.text_input("Usuario")
        new_pass = st.sidebar.text_input("Contraseña", type="password")
        if st.sidebar.button("Registrar"):
            if agregar_usuario(new_user, new_pass):
                st.sidebar.success("Cuenta creada. Ahora iniciá sesión.")
            else:
                st.sidebar.error("El usuario ya existe.")

    elif menu == "Iniciar Sesión":
        st.sidebar.subheader("Ingresar")
        username = st.sidebar.text_input("Usuario")
        password = st.sidebar.text_input("Contraseña", type="password")
        if st.sidebar.button("Entrar"):
            user_data = login_usuario(username, password)
            if user_data:
                st.session_state["user_id"] = user_data[0]
                st.session_state["username"] = username
                st.rerun()
            else:
                st.sidebar.error("Credenciales incorrectas")
else:
    st.sidebar.success(f"Hola, {st.session_state['username']}")
    if st.sidebar.button("Cerrar Sesión"):
        st.session_state["user_id"] = None
        st.session_state["username"] = None
        st.rerun()
        
    st.sidebar.markdown("---")
    st.sidebar.subheader("Configuración de Alertas (Gmail)")
    st.sidebar.info("Necesitás usar una Contraseña de Aplicación de Google.")
    email_config = st.sidebar.text_input("Tu Email (Gmail)")
    pass_config = st.sidebar.text_input("Contraseña de App", type="password")

# --- PANTALLA PRINCIPAL ---
if st.session_state["user_id"]:
    st.title("📊 Monitor de Cartera Valorizada")

    # Formulario para agregar activos
    with st.expander("➕ Agregar nueva posición a la cartera", expanded=False):
        with st.form("form_posicion"):
            c1, c2, c3, c4 = st.columns(4)
            f_especie = c1.text_input("Ticker (Ej: AAPL, YPF)")
            f_cantidad = c2.number_input("Cantidad Nominal", min_value=1)
            f_inversion = c3.number_input("Valor Invertido ($)", min_value=0.01, format="%.2f")
            f_ganancia = c4.number_input("% Ganancia Objetivo", min_value=0.1, format="%.2f", value=10.0)
            
            if st.form_submit_button("Guardar Posición"):
                if f_especie:
                    agregar_posicion(st.session_state["user_id"], f_especie, f_cantidad, f_inversion, f_ganancia)
                    st.success("¡Posición agregada!")
                    st.rerun()
                else:
                    st.error("El Ticker es obligatorio.")

    st.markdown("---")
    st.subheader("Tus Activos")
    posiciones = obtener_posiciones(st.session_state["user_id"])

    if not posiciones:
        st.info("No tenés activos en cartera. Agregá uno arriba.")
    else:
        # Iterar sobre las posiciones y mostrarlas en tarjetas
        for pos in posiciones:
            pos_id, especie, cantidad, inversion, ganancia_obj = pos
            
            try:
                # Consultar precio a Yahoo Finance
                ticker = yf.Ticker(especie)
                historial = ticker.history(period="1d")
                
                if historial.empty:
                    st.error(f"No se encontró información para el ticker {especie}.")
                    continue
                    
                precio_actual = historial['Close'].iloc[-1]
                
                # Cálculos
                saldo_valorizado = cantidad * precio_actual
                rendimiento_dinero = saldo_valorizado - inversion
                rendimiento_porc = (rendimiento_dinero / inversion) * 100
                monto_ganancia_deseado = inversion * (ganancia_obj / 100)
                nominales_a_vender = math.ceil(monto_ganancia_deseado / precio_actual)
                
                # Visualización
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([1, 1, 1, 1, 1])
                    col1.metric(f"📈 {especie} ({cantidad} nom)", f"${precio_actual:.2f}")
                    col2.metric("Inversión Inicial", f"${inversion:.2f}")
                    col3.metric("Saldo Actual", f"${saldo_valorizado:.2f}", f"{rendimiento_porc:.2f}%")
                    col4.metric("Objetivo de Ganancia", f"{ganancia_obj}%", f"${monto_ganancia_deseado:.2f}")
                    
                    with col5:
                        st.write("Acciones")
                        if st.button("🗑️ Eliminar", key=f"del_{pos_id}"):
                            eliminar_posicion(pos_id)
                            st.rerun()

                    # Lógica de Alerta
                    if rendimiento_dinero >= monto_ganancia_deseado:
                        st.warning(f"🎯 **¡OBJETIVO CUMPLIDO!** Vender **{nominales_a_vender} nominales** de {especie} para tomar tu ganancia de ${monto_ganancia_deseado:.2f}.")
                        
                        if email_config and pass_config:
                            if st.button("📧 Enviar Alerta por Mail", key=f"mail_{pos_id}"):
                                res = enviar_alerta(email_config, pass_config, especie, nominales_a_vender, precio_actual, monto_ganancia_deseado)
                                if res is True:
                                    st.success("¡Mail enviado!")
                                else:
                                    st.error(f"Error al enviar: {res}")
                        else:
                            st.caption("Configurá tu email y contraseña de app en la barra lateral para enviar correos.")
                st.divider()
                
            except Exception as e:
                st.error(f"Error procesando {especie}: {e}")

else:
    st.info("👈 Por favor, iniciá sesión o registrate en el panel lateral para ver tu cartera.")

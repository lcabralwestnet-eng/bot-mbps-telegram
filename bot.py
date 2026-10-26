import logging
import re
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Registrar logs en consola
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Servidor HTTP básico para satisfacer el Health Check de Render (Web Service)
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        self.wfile.write(b"Bot activo y funcionando 24/7")

def run_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    logging.info(f"Servidor HTTP escuchando en el puerto {port}")
    server.serve_forever()

# 1. Conexión con Google Sheets
scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]
creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
client = gspread.authorize(creds)

SPREADSHEET_ID = "18c-1_8pxgfzpuohcuhGOHl0WiHbQYJd7mQ5G1BYAaEA" 
sheet = client.open_by_key(SPREADSHEET_ID).sheet1

# 2. Mensaje inicial /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    mensaje = (
        "👋 ¡Hola! Soy el bot de consulta de equipos.\n\n"
        "Escríbeme o pega el modelo del equipo "
        "(ej: `ONU HUAWEI HG8145V5 DUAL BAND`, `Archer C5`, `8141H5`) "
        "y te diré cuántos Mbps soporta."
    )
    await update.message.reply_text(mensaje, parse_mode='Markdown')

# 3. Búsqueda inteligente por coincidencia de modelo
async def buscar_equipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto_raw = update.message.text.strip().lower()

    todas_las_filas = sheet.get_all_values()
    candidatos = []

    for fila in todas_las_filas:
        valores_limpios = [str(c).strip() for c in fila if str(c).strip() != ""]
        
        if not valores_limpios or len(valores_limpios) < 2:
            continue
        if "marca" in valores_limpios[0].lower() or "onu / router" in valores_limpios[0].lower():
            continue

        modelo_columna = valores_limpios[1].strip().lower() if len(valores_limpios) > 1 else ""

        if modelo_columna and (modelo_columna in texto_raw or texto_raw in modelo_columna):
            candidatos.append((len(modelo_columna), valores_limpios))
        else:
            palabras_modelo = [p for p in re.findall(r'\b\w+\b', modelo_columna) if len(p) >= 3]
            for pm in palabras_modelo:
                if pm in texto_raw:
                    candidatos.append((len(pm), valores_limpios))
                    break

    if candidatos:
        candidatos.sort(key=lambda x: x[0], reverse=True)
        coincidencia_exacta = candidatos[0][1]

        marca = coincidencia_exacta[0] if len(coincidencia_exacta) > 0 else "N/A"
        modelo = coincidencia_exacta[1] if len(coincidencia_exacta) > 1 else "N/A"
        bandas = coincidencia_exacta[2] if len(coincidencia_exacta) > 2 else "N/A"
        plan = coincidencia_exacta[3] if len(coincidencia_exacta) > 3 else "N/A"

        respuesta = (
            f"🏷️ **Marca:** {marca}\n"
            f"📱 **Modelo:** {modelo}\n"
            f"📡 **Bandas / Puertos:** {bandas}\n"
            f"🚀 **Plan Máximo Soportado:** {plan} Mbps"
        )
        await update.message.reply_text(respuesta, parse_mode='Markdown')
    else:
        await update.message.reply_text("❌ No encontré ningún equipo con ese modelo. Revisa la planilla de Google Sheets.")

# 4. Inicialización
if __name__ == '__main__':
    # Iniciar servidor web secundario en un hilo para Render
    server_thread = threading.Thread(target=run_health_check_server, daemon=True)
    server_thread.start()

    TELEGRAM_TOKEN = "8807699433:AAFPW3dtcZR-WDT5g0EOLEqbcjfvvqjYka8"
    
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, buscar_equipo))
    
    print("🤖 El bot está activo y escuchando consultas...")
    app.run_polling()

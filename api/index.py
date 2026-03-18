from fastapi import FastAPI
from fastapi.responses import RedirectResponse, HTMLResponse
from api.webhook import router as webhook_router
from api.dashboard import router as dashboard_router

app = FastAPI(title="Noduz WhatsApp Bot — Family Barber")
app.include_router(webhook_router)
app.include_router(dashboard_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "noduz-whatsapp-bot", "business": "Family Barber"}


@app.get("/")
async def root():
    return RedirectResponse(url="/dashboard")


@app.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return HTMLResponse(content="""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Política de Privacidad — Family Barber</title>
<style>
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 680px; margin: 60px auto; padding: 0 24px; color: #1a1a1a; line-height: 1.7; }
  h1 { font-size: 24px; font-weight: 600; margin-bottom: 8px; }
  h2 { font-size: 16px; font-weight: 600; margin-top: 32px; margin-bottom: 8px; }
  p, li { font-size: 15px; color: #444; }
  ul { padding-left: 20px; }
  .date { color: #888; font-size: 13px; margin-bottom: 32px; }
</style>
</head>
<body>
<h1>Política de Privacidad</h1>
<p class="date">Última actualización: marzo 2026</p>

<p>Family Barber utiliza un asistente virtual de WhatsApp para facilitar el agendamiento de citas. Esta política describe cómo manejamos tu información.</p>

<h2>Información que recopilamos</h2>
<ul>
  <li>Número de teléfono de WhatsApp</li>
  <li>Nombre de perfil de WhatsApp</li>
  <li>Mensajes enviados al asistente para coordinar citas</li>
  <li>Datos de la cita: servicio, fecha, hora y precio</li>
</ul>

<h2>Cómo usamos tu información</h2>
<ul>
  <li>Para agendar, confirmar y gestionar tu cita</li>
  <li>Para enviarte recordatorios o confirmaciones por WhatsApp</li>
  <li>Para mejorar el servicio de atención al cliente</li>
</ul>

<h2>Almacenamiento y seguridad</h2>
<p>Tu información se almacena de forma segura en servidores protegidos. No compartimos tu información personal con terceros, excepto lo necesario para procesar tu cita (Google Calendar).</p>

<h2>Retención de datos</h2>
<p>Conservamos el historial de conversaciones por un período máximo de 12 meses. Puedes solicitar la eliminación de tus datos en cualquier momento escribiéndonos por WhatsApp.</p>

<h2>Contacto</h2>
<p>Si tienes preguntas sobre esta política, contáctanos a través de WhatsApp en el mismo número del asistente.</p>
</body>
</html>""")

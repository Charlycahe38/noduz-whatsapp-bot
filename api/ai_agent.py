import json
import traceback
from datetime import date
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types

from api import config
from api.conversation import get_conversation, save_conversation
from api.whatsapp import send_message
from api.calendar_service import find_available_slots, create_calendar_event
from api.appointments import save_appointment

client = genai.Client(api_key=config.GEMINI_API_KEY)

TOOL_DEFINITIONS = [
    types.Tool(function_declarations=[
        types.FunctionDeclaration(
            name="check_calendar_availability",
            description=(
                "Check available time slots on the calendar for a specific date. "
                "ALWAYS use this before offering any time slots to the customer."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "date": types.Schema(
                        type=types.Type.STRING,
                        description="Date in YYYY-MM-DD format"
                    ),
                    "duration_minutes": types.Schema(
                        type=types.Type.INTEGER,
                        description="Service duration in minutes"
                    )
                },
                required=["date", "duration_minutes"]
            )
        ),
        types.FunctionDeclaration(
            name="create_appointment",
            description=(
                "Create a confirmed appointment in the calendar and database. "
                "Only call this AFTER the customer has explicitly confirmed."
            ),
            parameters=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "customer_name": types.Schema(type=types.Type.STRING),
                    "customer_phone": types.Schema(type=types.Type.STRING),
                    "service_name": types.Schema(type=types.Type.STRING),
                    "date": types.Schema(
                        type=types.Type.STRING,
                        description="YYYY-MM-DD"
                    ),
                    "start_time": types.Schema(
                        type=types.Type.STRING,
                        description="HH:MM"
                    ),
                    "duration_minutes": types.Schema(type=types.Type.INTEGER),
                    "price": types.Schema(type=types.Type.NUMBER),
                    "barber": types.Schema(
                        type=types.Type.STRING,
                        description="Name of the chosen barber (Daniel, Enrique, Juan, or Pedro)"
                    )
                },
                required=[
                    "customer_name", "customer_phone", "service_name",
                    "date", "start_time", "duration_minutes", "price"
                ]
            )
        )
    ])
]


def build_system_prompt() -> str:
    tz = ZoneInfo(config.TIMEZONE)
    today = date.today()

    day_names_es = [
        "Lunes", "Martes", "Miércoles", "Jueves",
        "Viernes", "Sábado", "Domingo"
    ]
    month_names_es = [
        "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
        "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
    ]

    current_day_name = day_names_es[today.weekday()]
    current_date_iso = today.isoformat()
    current_date_spanish = f"{current_day_name} {today.day} de {month_names_es[today.month]} de {today.year}"

    services_text = "\n".join(
        f"- {s['name']}: {s['duration']} minutos, ${s['price']} MXN"
        for s in config.SERVICES
    )

    barbers_text = ", ".join(config.BARBERS)

    return f"""Eres el asistente virtual de {config.BUSINESS_NAME}, una barbería en {config.BUSINESS_LOCATION}. Tu trabajo es ayudar a los clientes a agendar citas de forma natural, amigable y conversacional.

IDIOMA: Responde en español por defecto. Si el cliente escribe en inglés, responde en inglés. Sé bilingüe según lo que use el cliente.

## SERVICIOS DISPONIBLES

{services_text}

## BARBEROS DISPONIBLES

{barbers_text}

## HORARIO DE TRABAJO

- Días laborales: {config.WORKING_DAYS}
- Horario: 11:00 AM a 8:00 PM
- Descanso: 2:00 PM a 4:00 PM
- Zona horaria: America/Mexico_City

## CÓMO DEBES COMPORTARTE

1. Saluda al cliente de forma casual y amigable. Ejemplo de tono: "{config.BOT_GREETING_EXAMPLE}". NO uses menús numerados rígidos. Conversa naturalmente.
2. Pregunta qué servicio desea de forma conversacional.
3. Pregunta con qué barbero prefiere su cita ({barbers_text}).
4. Cuando el cliente elija fecha (puede decir "mañana", "el viernes", "hoy", etc.), usa check_calendar_availability con la duración correcta del servicio.
5. Presenta 4-6 horarios disponibles de forma conversacional, distribuidos entre mañana y tarde. NO muestres todos.
6. Cuando el cliente elija horario, muestra un resumen completo y pide confirmación explícita.
7. SOLO cuando el cliente confirme explícitamente ("sí", "dale", "perfecto", "va", "órale", "sí, está bien", "yes", "confirm"), usa create_appointment.
8. Después de crear la cita, envía la confirmación con todos los detalles.

## CÓMO INTERPRETAR FECHAS

- "hoy" / "today" = {current_date_iso}
- "mañana" / "tomorrow" = día siguiente
- "pasado mañana" = dos días después
- "el lunes", "el martes", etc. = el próximo día con ese nombre
- Fecha de hoy: {current_date_spanish} ({current_date_iso})
- Día de la semana: {current_day_name}

## REGLAS QUE NUNCA PUEDES ROMPER

- NUNCA inventes horarios. SIEMPRE usa check_calendar_availability antes de ofrecer cualquier horario.
- NUNCA crees una cita sin confirmación explícita del cliente.
- No agendes en el horario de descanso (2:00 PM - 4:00 PM).
- No agendes antes de las 11:00 AM ni después de las 8:00 PM.
- El último turno posible es la hora de cierre MENOS la duración del servicio.
- No agendes en fechas pasadas.
- Si no hay disponibilidad, sugiere amablemente otro día cercano.
- Si el cliente pregunta algo fuera del agendamiento, responde brevemente y redirige.
- NUNCA menciones que eres una IA, bot o sistema automatizado.
- Si el cliente quiere cancelar el proceso, responde amablemente y ofrece agendar en otro momento.

## FORMATO DE CONFIRMACIÓN

Cuando la cita esté creada exitosamente, envía EXACTAMENTE este formato:

Tu cita ha sido confirmada. ✓

Servicio: [nombre del servicio]
Barbero: [nombre del barbero]
Fecha: [fecha en español, ej: Viernes 21 de marzo de 2026]
Hora: [hora inicio] - [hora fin]
Precio: $[precio] MXN

{config.POST_CONFIRMATION_MESSAGE}

{config.CANCELLATION_POLICY}
"""


async def execute_tool(tool_name: str, args: dict) -> str:
    if tool_name == "check_calendar_availability":
        try:
            slots = find_available_slots(args["date"], args["duration_minutes"])
            if not slots:
                return f"No hay horarios disponibles para {args['date']}. Por favor sugiere al cliente otro día cercano."
            return f"Horarios disponibles para {args['date']}: {', '.join(slots)}"
        except Exception as e:
            print(f"Calendar error: {e}")
            return "Error al consultar el calendario. Informa al cliente que intente en unos minutos."

    elif tool_name == "create_appointment":
        try:
            barber = args.get("barber", "")
            title = f"✂️ {args['service_name']} - {args['customer_name']}"
            if barber:
                title += f" ({barber})"

            description = (
                f"Cliente: {args['customer_name']}\n"
                f"Teléfono: {args['customer_phone']}\n"
                f"Servicio: {args['service_name']}\n"
                f"Barbero: {barber}\n"
                f"Precio: ${args['price']} MXN"
            )

            event_id = create_calendar_event(
                title, description,
                args["date"], args["start_time"], args["duration_minutes"]
            )

            # Calculate end time
            start_parts = args["start_time"].split(":")
            start_minutes = int(start_parts[0]) * 60 + int(start_parts[1])
            end_minutes = start_minutes + args["duration_minutes"]
            end_time = f"{end_minutes // 60:02d}:{end_minutes % 60:02d}"

            await save_appointment({
                **args,
                "end_time": end_time,
                "google_event_id": event_id
            })

            return f"Cita creada exitosamente. ID: {event_id}. Hora fin: {end_time}"
        except Exception as e:
            print(f"Appointment creation error: {e}\n{traceback.format_exc()}")
            return "Error al crear la cita. Por favor informa al cliente y pide que intente de nuevo."

    return "Herramienta no reconocida."


async def handle_incoming_message(customer_phone: str, customer_name: str, message_body: str):
    try:
        # Load history
        history = await get_conversation(customer_phone)

        # Append new user message
        history.append({"role": "user", "parts": [{"text": message_body}]})

        system_prompt = build_system_prompt()

        # Convert history to genai Contents format
        contents = []
        for msg in history:
            role = msg["role"]
            text = msg["parts"][0]["text"] if msg.get("parts") else ""
            contents.append(types.Content(
                role=role,
                parts=[types.Part(text=text)]
            ))

        # Call Gemini
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                tools=TOOL_DEFINITIONS,
                temperature=0.7
            )
        )

        # Handle tool calls in a loop
        max_iterations = 5
        for _ in range(max_iterations):
            candidate = response.candidates[0]
            parts = candidate.content.parts

            # Check if there are function calls
            function_calls = [p for p in parts if p.function_call]

            if not function_calls:
                # No more tool calls — get the final text
                break

            # Execute each tool call
            tool_results = []
            for part in function_calls:
                fc = part.function_call
                tool_name = fc.name
                tool_args = dict(fc.args)

                print(f"Tool call: {tool_name}({tool_args})")
                result = await execute_tool(tool_name, tool_args)
                print(f"Tool result: {result}")

                tool_results.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=tool_name,
                        response={"result": result}
                    )
                ))

            # Feed tool results back
            contents.append(types.Content(
                role="model",
                parts=parts
            ))
            contents.append(types.Content(
                role="user",
                parts=tool_results
            ))

            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=TOOL_DEFINITIONS,
                    temperature=0.7
                )
            )

        # Extract final text response
        final_text = ""
        for part in response.candidates[0].content.parts:
            if part.text:
                final_text += part.text

        if not final_text:
            final_text = "Disculpa, hubo un problema. Por favor intenta de nuevo."

        # Send WhatsApp message
        await send_message(customer_phone, final_text)

        # Save updated conversation
        history.append({"role": "model", "parts": [{"text": final_text}]})
        await save_conversation(customer_phone, customer_name, history)

    except Exception as e:
        print(f"handle_incoming_message error: {e}\n{traceback.format_exc()}")
        try:
            await send_message(
                customer_phone,
                "⚠️ Hubo un error inesperado. Por favor intenta de nuevo en un momento."
            )
        except Exception:
            pass

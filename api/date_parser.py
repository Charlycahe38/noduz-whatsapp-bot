from datetime import date, timedelta
import re


def parse_spanish_date(text: str) -> str | None:
    """Parse Spanish date expressions and return YYYY-MM-DD string."""
    text_lower = text.lower().strip()
    today = date.today()

    if text_lower in ["hoy", "today"]:
        return today.isoformat()
    if text_lower in ["mañana", "manana", "tomorrow"]:
        return (today + timedelta(days=1)).isoformat()
    if text_lower in ["pasado mañana", "pasado manana"]:
        return (today + timedelta(days=2)).isoformat()

    day_map = {
        "lunes": 0, "martes": 1, "miércoles": 2, "miercoles": 2,
        "jueves": 3, "viernes": 4, "sábado": 5, "sabado": 5, "domingo": 6,
        "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
        "friday": 4, "saturday": 5, "sunday": 6
    }
    for name, weekday in day_map.items():
        if name in text_lower:
            days_ahead = (weekday - today.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7
            return (today + timedelta(days=days_ahead)).isoformat()

    # DD/MM/YYYY or DD-MM-YYYY
    match = re.search(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', text)
    if match:
        day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None

    return None

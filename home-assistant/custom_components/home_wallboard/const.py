"""Settings exposed as standard Home Assistant entities."""

DOMAIN = "home_wallboard"
PLATFORMS = ["switch", "select", "number", "time", "button", "sensor", "binary_sensor"]
SWITCHES = {
    "presence_enabled": ("Camera wake", "Kameraväckning"),
    "keyboard_auto": ("Automatic keyboard", "Automatiskt tangentbord"),
    "show_weather": ("Show weather", "Visa väder"),
    "show_home": ("Show home status", "Visa hemstatus"),
    "show_people": ("Show people", "Visa närvaro"),
    "show_lights": ("Show lights", "Visa belysning"),
    "show_temperatures": ("Show temperatures", "Visa temperaturer"),
    "show_photos": ("Show slideshow button", "Visa bildspelsknapp"),
    "show_help_text": ("Show help text", "Visa hjälptext"),
    "night_mode_enabled": ("Night mode", "Nattläge"),
}
ENUMS = {
    "theme": (["auto", "morning", "day", "evening", "night", "dark"], "Theme", "Tema"),
    "language": (["sv", "en"], "Language", "Språk"),
    "time_format": (["24h", "12h"], "Time format", "Tidsformat"),
    "screen_mode": (["photos", "dim", "keep_on"], "Idle mode", "Viloläge"),
    "start_dashboard": (["home", "planner", "security", "music"], "Startup dashboard", "Startvy"),
    "timer_sound": (["chime", "bell", "digital", "piano", "gong"], "Timer sound", "Timerljud"),
    "timer_outputs": (["tablet", "sonos", "both"], "Timer audio outputs", "Ljudenheter för timer"),
    "photo_source": (["immich", "local", "icloud", "google"], "Photo source", "Bildkälla"),
    "outdoor_temperature_source": (
        ["sensor", "weather"],
        "Outdoor temperature source",
        "Källa för utetemperatur",
    ),
    "weather_source": (["ha", "open_meteo"], "Forecast source", "Väderkälla"),
    "active_dashboard": (["home", "planner", "security", "music"], "Active dashboard", "Aktiv vy"),
}
DYNAMIC = {
    "indoor_temperature_entity": ("temperature_sensors", "Indoor sensor", "Inomhusgivare"),
    "outdoor_temperature_entity": ("temperature_sensors", "Outdoor sensor", "Utomhusgivare"),
    "weather_entity": ("weather_entities", "HA weather entity", "Väderentitet i HA"),
    "photo_album": ("photo_albums", "Slideshow album", "Bildspelsalbum"),
}
NUMBERS = {
    "idle_seconds": (15, 3600, "s", "Idle timeout", "Tid till viloläge"),
    "slide_seconds": (5, 300, "s", "Photo duration", "Tid per bild"),
    "active_brightness": (20, 100, "%", "Active brightness", "Aktiv ljusstyrka"),
    "idle_brightness": (1, 60, "%", "Idle brightness", "Ljusstyrka vid vila"),
    "timer_volume": (0, 100, "%", "Timer volume", "Timervolym"),
}
TIMES = {
    "night_start": ("Night starts", "Nattläge börjar"),
    "night_end": ("Night ends", "Nattläge slutar"),
}
BUTTONS = {
    "wake": ("Wake screen", "Väck skärmen"),
    "sleep": ("Turn screen off", "Släck skärmen"),
    "refresh": ("Refresh status", "Uppdatera status"),
}
SENSORS = {
    "mode": ("Display mode", "Skärmläge"),
    "brightness": ("Current brightness", "Aktuell ljusstyrka"),
    "selected_lights": ("Selected lights", "Valda lampor"),
    "photos": ("Available slideshow photos", "Tillgängliga bilder"),
    "location": ("Weather location", "Väderplats"),
}
BINARY = {
    "online": ("Control connection", "Kontrollanslutning"),
    "camera_ok": ("Presence camera", "Närvarokamera"),
    "ha_online": ("HA connection", "HA-anslutning"),
    "immich_online": ("Immich connection", "Immich-anslutning"),
    "fire_active": ("Fire alarm active", "Brandlarm aktivt"),
}

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
from gi.repository import Gdk, Gio, Gtk

LIGHT_SELECTION = "#ffffff"
DARK_SELECTION = "#1e1e1e"

LIGHT_RAINBOW = [
    "#c0392b",
    "#9d640b",
    "#1e8449",
    "#117a8b",
    "#1a5490",
    "#7d3c98",
    "#9c4a1a",
    "#177a76",
]

DARK_RAINBOW = [
    "#e06c75",
    "#e5c07b",
    "#98c379",
    "#56b6c2",
    "#61afef",
    "#c678dd",
    "#d19a66",
    "#5fb3b3",
]


def rgba(value):
    color = Gdk.RGBA()
    color.parse(value)
    return color


def luminance(color):
    return 0.299 * color.red + 0.587 * color.green + 0.114 * color.blue


def surface_color(widget):
    try:
        color = widget.get_style_context().get_property("background-color", Gtk.StateFlags.NORMAL)
    except Exception:
        color = None
    if color is None or color.alpha == 0:
        color = rgba("#1e1e1e" if is_dark() else "#ffffff")
    return rgba("rgb({},{},{})".format(
        round(color.red * 255), round(color.green * 255), round(color.blue * 255)
    ))


def mix(first, second, ratio):
    result = Gdk.RGBA()
    result.red = first.red * (1 - ratio) + second.red * ratio
    result.green = first.green * (1 - ratio) + second.green * ratio
    result.blue = first.blue * (1 - ratio) + second.blue * ratio
    result.alpha = 1.0
    return result


def is_dark(widget=None):
    settings = Gtk.Settings.get_default()
    if settings is not None:
        if settings.get_property("gtk-application-prefer-dark-theme"):
            return True
        name = settings.get_property("gtk-theme-name") or ""
        if "dark" in name.lower():
            return True
    try:
        if Gio.Settings.new("org.gnome.desktop.interface").get_string("color-scheme") == "prefer-dark":
            return True
    except Exception:
        pass
    return widget is not None and luminance(surface_color(widget)) < 0.5


def column_color(index, dark=None):
    if dark is None:
        dark = is_dark()
    palette = DARK_RAINBOW if dark else LIGHT_RAINBOW
    return rgba(palette[index % len(palette)])


def line_number_color(dark=None):
    if dark is None:
        dark = is_dark()
    return rgba("#9aa0a6" if dark else "#5f6672")


def selection_color(widget=None):
    return rgba(DARK_SELECTION if is_dark(widget) else LIGHT_SELECTION)


def background_color(widget, index, bad=False, dark=None):
    if dark is None:
        dark = is_dark(widget)
    base = surface_color(widget)
    if bad:
        return mix(base, rgba("#ff6b6b" if dark else "#c0392b"), 0.35)
    if index % 2:
        return mix(base, rgba("#ffffff" if dark else "#000000"), 0.07 if dark else 0.04)
    return base


def sync_system_settings():
    settings = Gtk.Settings.get_default()
    if settings is None:
        return
    try:
        scheme = Gio.Settings.new("org.gnome.desktop.interface").get_string("color-scheme")
    except Exception:
        return
    if "dark" in (settings.get_property("gtk-theme-name") or "").lower():
        return
    desired = scheme == "prefer-dark"
    if settings.get_property("gtk-application-prefer-dark-theme") != desired:
        settings.set_property("gtk-application-prefer-dark-theme", desired)


def connect_settings(callback):
    handlers = []
    settings = Gtk.Settings.get_default()
    if settings is not None:
        for signal in ("notify::gtk-theme-name", "notify::gtk-application-prefer-dark-theme"):
            handlers.append((settings, settings.connect(signal, callback)))
    try:
        desktop = Gio.Settings.new("org.gnome.desktop.interface")
        handlers.append((desktop, desktop.connect("changed::color-scheme", callback)))
    except Exception:
        pass
    return handlers


def disconnect_settings(handlers):
    for obj, handler in handlers:
        obj.disconnect(handler)

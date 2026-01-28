"""Translations for NapisyTWON."""

TRANSLATIONS = {
    "pl": {
        # Menus
        "&File": "&Plik",
        "&Open PDF...": "&Otwórz PDF...",
        "&Save": "&Zapisz",
        "Save &As...": "Zapisz &jako...",
        "Recent Files": "Ostatnie pliki",
        "Clear Recent": "Wyczyść ostatnie",
        "E&xit": "&Wyjście",
        "&Edit": "&Edycja",
        "&Undo": "&Cofnij",
        "&Redo": "&Ponów",
        "&Delete Selected": "&Usuń zaznaczony",
        "Clear &All Numbers": "Usuń &wszystkie numery",
        "&View": "&Widok",
        "Zoom &In": "Po&większ",
        "Zoom &Out": "Po&mniejsz",
        "&Fit to Window": "&Dopasuj do okna",
        "&Actual Size": "&Rzeczywisty rozmiar",
        "&Next Page": "&Następna strona",
        "&Previous Page": "&Poprzednia strona",
        "&Style": "&Styl",
        "Style &Presets...": "&Szablony stylów...",
        "Save Current as Default": "Zapisz bieżący jako domyślny",
        "Reset Style to Defaults": "Przywróć domyślny styl",

        # Toolbar
        " Tool: ": " Narzędzie: ",
        "Insert": "Wstaw",
        "Select": "Zaznacz",
        " Next #: ": " Następny #: ",
        " Font: ": " Czcionka: ",
        " Size: ": " Rozmiar: ",
        " Text: ": " Tekst: ",
        " BG: ": " Tło: ",
        " Opacity: ": " Krycie: ",
        " Page: ": " Strona: ",
        "Zoom:": "Powiększenie:",
        "Border": "Ramka",
        "Border width": "Grubość ramki",
        "Tail": "Linia",
        " L:": " D:",
        "Tail length": "Długość linii",
        " W:": " G:",
        "Tail width": "Grubość linii",
        "Apply to Selected": "Zastosuj do zaznaczonego",
        "Presets": "Szablony",

        # Dialogs
        "Style Presets": "Szablony stylów",
        "New preset name...": "Nazwa nowego szablonu...",
        "Save Current": "Zapisz bieżący",
        "Delete": "Usuń",
        "Load": "Wczytaj",
        "Close": "Zamknij",
        "Open PDF": "Otwórz PDF",
        "PDF Files (*.pdf);;All Files (*.*)": "Pliki PDF (*.pdf);;Wszystkie pliki (*.*)",
        "Save PDF As": "Zapisz PDF jako",
        "PDF Files (*.pdf)": "Pliki PDF (*.pdf)",
        "Unsaved Changes": "Niezapisane zmiany",
        "There are unsaved changes. Do you want to save?": "Są niezapisane zmiany. Czy chcesz zapisać?",
        "Clear All": "Usuń wszystko",
        "Delete all annotations?": "Usunąć wszystkie adnotacje?",
        "Number Already Exists": "Numer już istnieje",
        "What would you like to do?": "Co chcesz zrobić?",
        "Auto-advance others": "Automatycznie przesuń pozostałe",
        "Use sub-number": "Użyj podnumeru",
        "Change Number": "Zmień numer",
        "Delete Annotation": "Usuń adnotację",
        "Do you want to auto-decrease following numbers?": "Czy automatycznie zmniejszyć następne numery?",
        "Delete && decrease others": "Usuń i zmniejsz pozostałe",
        "Delete only": "Tylko usuń",
        "Save": "Zapisz",
        "Discard": "Odrzuć",
        "Cancel": "Anuluj",

        # Error Messages
        "Error": "Błąd",
        "Please enter a name for the preset.": "Podaj nazwę szablonu.",
        "Cannot delete the default preset.": "Nie można usunąć domyślnego szablonu.",
        "File Not Found": "Nie znaleziono pliku",
        "File not found:": "Nie znaleziono pliku:",
        "Could not open file:": "Nie można otworzyć pliku:",
        "Save Error": "Błąd zapisu",
        "Invalid Number": "Nieprawidłowy numer",
        "Please enter a valid number (e.g., 67 or 67.1)": "Podaj prawidłowy numer (np. 67 lub 67.1)",

        # Status Bar Messages
        "Ready": "Gotowe",
        "Current style saved as default": "Bieżący styl zapisany jako domyślny",
        "Style reset to defaults": "Styl przywrócony do domyślnego",
        "Opened:": "Otwarto:",
        "annotations": "adnotacji",
        "Saved:": "Zapisano:",
        "Selected:": "Zaznaczono:",
        "Added:": "Dodano:",
        "Deleted:": "Usunięto:",
        "Deleted": "Usunięto",
        "Changed:": "Zmieniono:",
        "Changed": "Zmieniono",
        "to": "na",
        "Tool:": "Narzędzie:",
        "Applied style to": "Zastosowano styl do",
        "Undo:": "Cofnij:",
        "Redo:": "Ponów:",
        "Cleared all annotations": "Usunięto wszystkie adnotacje",
        "Inserted": "Wstawiono",
        "advanced": "przesunięto",
        "decreased": "zmniejszono",
        "others": "innych",
        "Number": "Numer",
        "already exists.": "już istnieje.",
        "Enter new number for": "Podaj nowy numer dla",
        "Delete annotation": "Usunąć adnotację",

        # Other
        "Default": "Domyślny",
        "Main Toolbar": "Główny pasek narzędzi",

        # Language menu
        "&Language": "&Język",
        "English": "English",
        "Polski": "Polski",
    },
    "en": {}  # English is the default, no translation needed
}


class Translator:
    """Simple translator class."""

    _instance = None
    _language = "pl"  # Default to Polish

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def set_language(cls, lang: str):
        cls._language = lang

    @classmethod
    def get_language(cls) -> str:
        return cls._language

    @classmethod
    def tr(cls, text: str) -> str:
        """Translate text to current language."""
        if cls._language == "en":
            return text
        return TRANSLATIONS.get(cls._language, {}).get(text, text)


def tr(text: str) -> str:
    """Shortcut function for translation."""
    return Translator.tr(text)

""" Importable singleton instance of a Rich `Console` object. """
from rich.console import Console
from rich.theme import Theme

console = Console(
    color_system="auto",
    theme=Theme({
        "logging.level.trace": "dodger_blue1",
        "logging.level.print": "white",
    }),
)

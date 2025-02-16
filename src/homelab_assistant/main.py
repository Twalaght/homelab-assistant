
""" Runner entrypoint for HomeLab Assistant. """
import importlib
import pkgutil
from types import ModuleType

from homelab_assistant import runners
from homelab_assistant.utils import cli, logging

logger = logging.getLogger(__name__)


def import_package_modules(package: ModuleType) -> None:
    """ Import all modules of a package recursively.

    Args:
        package (ModuleType): Base package to import all modules from.
    """
    for _, name, is_pkg in pkgutil.walk_packages(package.__path__):
        # Resolve the full name of the module and import it
        module = importlib.import_module(f"{package.__name__}.{name}")

        # If the module itself is a package, begin recursively importing
        if is_pkg:
            import_package_modules(module)


import_package_modules(runners)


def main() -> None:
    """ Entrypoint runner. """
    args = cli.__ROOT_PARSER.parse_args()
    logging.setup_logger(verbosity=args.verbose)
    cli.run(args)


if __name__ == "__main__":
    main()

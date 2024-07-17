
""" Runner entrypoint for HomeLab Assistant. """
import argparse
from pathlib import Path

import cattrs
import yaml
from rich.console import Console

from homelab_assistant.config import Config
from homelab_assistant.portainer import PortainerHelper


def parent_parser() -> argparse.ArgumentParser:
    """ Template for bottom level "leaf" parsers. """
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-c", "--config", required=True,
                        help="YAML file to source configuration data from.")
    return parser


def export(args: argparse.Namespace, config: Config, portainer_connector: PortainerHelper) -> None:
    """ `export` entrypoint runner. """
    del config  # Specific config is not used in export

    stack_data = portainer_connector.export_config_from_stacks()
    with Path(args.export_file).open("w") as f:
        yaml.dump(stack_data, f, indent=4)


def sync(args: argparse.Namespace, config: Config, portainer_connector: PortainerHelper) -> None:
    """ `sync` entrypoint runner. """
    portainer_connector.sync_stacks(config, args.dry_run)


__ROOT_PARSER = argparse.ArgumentParser(add_help=True)
__ROOT_SUBPARSERS = __ROOT_PARSER.add_subparsers(required=True)

EXPORT_PARSER = __ROOT_SUBPARSERS.add_parser("export", parents=[parent_parser()])
EXPORT_PARSER.set_defaults(entry_func=export)
EXPORT_PARSER.add_argument("export_file")

SYNC_PARSER = __ROOT_SUBPARSERS.add_parser("sync", parents=[parent_parser()])
SYNC_PARSER.add_argument("--dry-run", action=argparse.BooleanOptionalAction,
                         help="Preview sync changes without making them")
SYNC_PARSER.set_defaults(entry_func=sync)

console = Console()


def main() -> None:
    """ Entrypoint runner. """
    args = __ROOT_PARSER.parse_args()

    with Path(args.config).open() as f:
        config_data = yaml.safe_load(f)
        config = cattrs.structure(config_data, Config)

    portainer_connector = PortainerHelper(
        api_key=config.portainer.api_key,
        portainer_url=config.portainer.url,
    )

    args.entry_func(args, config, portainer_connector)


if __name__ == "__main__":
    main()

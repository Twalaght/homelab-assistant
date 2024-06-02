
""" Runner entrypoint for HomeLab Assistant. """
import argparse
from pathlib import Path

import yaml
from rich.console import Console

from homelab_assistant.portainer import PortainerHelper

parser = argparse.ArgumentParser()
parser.add_argument("-e", "--export", metavar="EXPORT_FILE",
                    help="Export current Portainer environment to a file.")
parser.add_argument("-s", "--sync", default=None,
                    choices=["file", "git", "all"],
                    help="Type of Portainer stack to synchronise with config defined environment.")
parser.add_argument("config", metavar="CONFIG_FILE",
                    help="Config file defining common and stack specific environment variables")

console = Console()


def main() -> None:
    """ Entrypoint runner. """
    args = parser.parse_args()

    with Path(args.config).open() as f:
        config = yaml.safe_load(f)

    # Initialise the portainer connector
    portainer_connector = PortainerHelper(
        api_key=config["portainer"]["api_key"],
        portainer_url=config["portainer"]["url"],
    )

    if args.export:
        example = portainer_connector.export_config_from_stacks()
        with Path(args.export).open("w") as f:
            yaml.dump(example, f, indent=4)

    if args.sync:
        sync_file = args.sync in ("file", "all")
        sync_git = args.sync in ("git", "all")
        portainer_connector.sync_stack_envs(config, sync_file, sync_git)


if __name__ == "__main__":
    main()

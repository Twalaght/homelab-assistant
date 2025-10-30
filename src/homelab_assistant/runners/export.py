""" Runner module to export existing Portainer stacks to local config. """
import argparse
from pathlib import Path

import yaml

from homelab_assistant.helpers.portainer import PortainerHelper
from homelab_assistant.models.config import Config
from homelab_assistant.utils import cli, logging

logger = logging.getLogger(__name__)

_PARSER = cli.add_parser("export")
_PARSER.add_argument("config_file", help="YAML file to source configuration data from.")
_PARSER.add_argument("export_file", help="YAML file to write configuration data to.")


@cli.entrypoint(_PARSER)
def sync(args: argparse.Namespace) -> None:
    """ Export Portainer stacks to local config. """
    # Load config from the provided config file.
    with Path(args.config_file).open() as f:
        config_data = yaml.safe_load(f)
        config = Config(**config_data)
        config.check()

    portainer_connector = PortainerHelper(
        api_key=config.portainer.api_key,
        portainer_url=config.portainer.url,
    )

    output = {endpoint_name: endpoint_stack_info.model_dump(exclude_none=True)
              for endpoint_name, endpoint_stack_info in portainer_connector.export_stack_env_from_endpoints().items()}
    with Path(args.export_file).open("w") as f:
        yaml.dump(output, f, indent=4)

    logger.print(f"Portainer stacks exported to '{args.export_file}'")

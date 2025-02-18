""" Runner module to sync Portainer stacks with local config. """
import argparse
import difflib
from pathlib import Path

import yaml
from requests import HTTPError

from homelab_assistant.helpers.portainer import PortainerHelper
from homelab_assistant.models.config import Config
from homelab_assistant.utils import cli, logging

logger = logging.getLogger(__name__)

_PARSER = cli.add_parser("sync")
_PARSER.add_argument("--push", action="store_true", default=False, help="Sync changes to Portainer.")
_PARSER.add_argument("config_file", help="YAML file to source configuration data from.")


@cli.entrypoint(_PARSER)
def sync(args: argparse.Namespace) -> None:
    """ Sync Portainer stacks with local config. """
    # Load config from the provided config file.
    with Path(args.config_file).open() as f:
        config_data = yaml.safe_load(f)
        config = Config(**config_data)
        config.check()

    portainer_connector = PortainerHelper(
        api_key=config.portainer.api_key,
        portainer_url=config.portainer.url,
    )

    # Create a list of all stack names defined in Portainer, and local config.
    portainer_stack_info = portainer_connector.get_stacks()
    all_stack_names = sorted({*portainer_stack_info.keys(), *config.stacks.keys()})

    for stack_name in all_stack_names:
        portainer_info = portainer_stack_info.get(stack_name, None)
        config_info = config.stacks.get(stack_name, None)

        if not config_info:
            logger.warning(f"'{stack_name}': Defined only in [blue]Portainer[/]")
            continue

        if not portainer_info:
            # TODO - Eventually support new deployments.
            logger.warning(f"'{stack_name}': Defined only in [green]local config[/]")
            continue

        logger.info(f"'{stack_name}': Starting processing...")

        # If the stack is not required to be synced, continue.
        if not config_info.sync:
            logger.print(f"'{stack_name}': Sync set to disable, skipping")
            continue

        # Extract stack info from the Portainer data.
        stack_id = portainer_info["Id"]
        endpoint_id = portainer_info["EndpointId"]

        # Fetch the Portainer compose file, and a Git compose file if it is defined.
        git_compose = portainer_connector.get_git_compose_file(stack_name, config)
        portainer_compose = portainer_connector.get_stack_compose_file(stack_id)

        # Set the compose file and generate the required environment variables.
        compose = git_compose or portainer_compose
        required_env_vars = portainer_connector.get_defined_env_vars(compose)
        try:
            config_env = portainer_connector.generate_env_values_from_config(required_env_vars, config, stack_name)
        except ValueError:
            continue

        # Check if config or compose file need updating.
        portainer_env = {env["name"]: env["value"] for env in portainer_info["Env"]}
        if (config_env == portainer_env) and (compose == portainer_compose):
            logger.print(f"'{stack_name}': [blue]Nothing to do[/]")
            continue

        # Log out the compose different to update if the files did not match.
        if compose != portainer_compose:
            for line in difflib.unified_diff(portainer_compose.splitlines(), compose.splitlines(), lineterm=""):
                colour = "default"
                if line.startswith("+"):
                    colour = "green"
                elif line.startswith("-"):
                    colour = "red"

                logger.info(f"[{colour}]{line}[/]")

        # Add required environment variables and compose file to the update payload.
        payload = {
            "env": [
                {"name": name, "value": value} for name, value in config_env.items()
            ],
            "stackFileContent": compose,
        }

        if not args.push:
            logger.print(f"'{stack_name}': [green]Ready to update[/]")
            continue

        # Update the stack with the generated payload.
        logger.print(f"'{stack_name}': Updating...")
        deploy_url = (f"{portainer_connector.portainer_url}/api/stacks/{stack_id}?endpointId={endpoint_id}")
        try:
            response = portainer_connector.session.put(deploy_url, json=payload)
            response.raise_for_status()
        except HTTPError:
            logger.exception(f"'{stack_name}': [red]Unable to update[/]")

        logger.print(f"'{stack_name}': [green]Successfully updated[/]")

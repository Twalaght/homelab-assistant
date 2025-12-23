""" Runner module to sync Portainer stacks with local config. """
import argparse
import difflib
from typing import Any

from fluffless.utils import cli, logging
from requests import HTTPError

from homelab_assistant.helpers.portainer import PortainerHelper
from homelab_assistant.models.config import Config
from homelab_assistant.utils.cli import leaf_parser

PARSER = cli.add_parser(
    name="sync",
    parents=[leaf_parser()],
    help="Synchronise local config with Portainer.",
)
PARSER.add_argument("--push", action="store_true", default=False, help="Sync changes to Portainer.")

logger = logging.getLogger(__name__)


@cli.entrypoint(PARSER)
def sync(args: argparse.Namespace, config: Config) -> None:
    """ Sync Portainer stacks with local config. """
    # Create a Portainer helper from config.
    portainer_helper = PortainerHelper(
        api_key=config.portainer.api_key,
        portainer_url=config.portainer.url,
    )

    # Exit early if there are no stacks to stacks at all on Portainer.
    if not (endpoint_stack_info := portainer_helper.get_stacks()):
        logger.print("No stacks defined in Portainer")
        return

    for endpoint_name, stack_info in endpoint_stack_info.items():
        # Skip the endpoint if no local config was defined for it.
        if endpoint_name not in config.endpoints:
            logger.info(f"No config defined for endpoint '{endpoint_name}'")
            continue

        logger.print(f"Syncing with endpoint '{endpoint_name}'")
        sync_endpoint(config, portainer_helper, endpoint_name, stack_info, args.push)


def sync_endpoint(config: Config, portainer_helper: PortainerHelper, endpoint_name: str,
                  stack_info: dict[str, dict[str, Any]], push: bool = False) -> None:
    """ Synchronise a given endpoint on Portainer with stack information defined in config.

    Args:
        config (Config): Config model with definitions of stacks for the given endpoint.
        portainer_helper (PortainerHelper): Portainer helper instance to interact with Portainer.
        endpoint_name (str): Name of the Portainer endpoint to consider.
        stack_info (dict[str, dict[str, Any]]): Existing stack information, sourced from Portainer.
        push (bool, optional): Push changes to Portainer. Defaults to False, where changes will \
                               be printed, but not pushed upstream.
    """
    # Create a list of all stack names defined in Portainer, and local config.
    all_stack_names = sorted({*stack_info.keys(), *config.endpoints[endpoint_name].stacks.keys()})

    for stack_name in all_stack_names:
        portainer_info = stack_info.get(stack_name)
        config_info = config.endpoints[endpoint_name].stacks.get(stack_name, None)

        if not config_info:
            logger.warning(f"'{stack_name}': Defined only in [blue]Portainer[/]")
            continue

        if not portainer_info:
            # TODO - Eventually support new deployments.
            logger.warning(f"'{stack_name}': Defined only in [green]local config[/]")
            continue

        logger.debug(f"'{stack_name}': Starting processing...")

        # If the stack is not required to be synced, continue.
        if not config_info.sync:
            logger.print(f"'{stack_name}': Sync set to disable, skipping")
            continue

        # Extract stack info from the Portainer data.
        stack_id = portainer_info["Id"]
        endpoint_id = portainer_info["EndpointId"]

        # Fetch the Portainer compose file, and a Git compose file if it is defined.
        git_compose = portainer_helper.get_git_compose_file(endpoint_name, stack_name, config) or ""
        portainer_compose = portainer_helper.get_stack_compose_file(stack_id) or ""

        # Set the compose file and generate the required environment variables.
        if not (compose := git_compose or portainer_compose):
            logger.error("No compose provided from Git or Portainer")
            continue

        required_env_vars = portainer_helper.get_defined_env_vars(compose)
        try:
            config_environment = portainer_helper.generate_env_values_from_config(
                required_env_vars, config, endpoint_name, stack_name,
            )
        except ValueError:
            continue

        # Construct environment mapping from existing environment in Portainer.
        portainer_environment = {env["name"]: env["value"] for env in portainer_info["Env"]}

        # Continue if there is no action to be taken.
        if (portainer_environment == config_environment) and (portainer_compose == compose):
            logger.print(f"'{stack_name}': [blue]Nothing to do[/]")
            continue

        if not push:
            logger.print(f"'{stack_name}': [green]Ready to update[/]")

        # Display diffs for both the environment and compose files.
        if portainer_environment != config_environment:
            display_environment_diff(base_environment=portainer_environment, new_environment=config_environment)
        if portainer_compose != compose:
            display_compose_diff(base_compose=portainer_compose, new_compose=compose)

        # If not syncing, exit early.
        if not push:
            continue

        # Add required environment variables and compose file to the update payload, and update the stack.
        try:
            portainer_helper.update_stack(
                endpoint_id=endpoint_id,
                stack_id=stack_id,
                compose=compose,
                environment=config_environment,
            )
            logger.print(f"'{stack_name}': [green]Successfully updated[/]")
        except HTTPError:
            logger.exception(f"'{stack_name}': [red]Unable to update[/]")


def display_environment_diff(base_environment: dict[str, str], new_environment: dict[str, str]) -> None:
    """ Display a diff between a base and new environment definitions. """
    logger.info("Environment diff:")
    if (added_keys := (set(new_environment) - set(base_environment))):
        logger.info(f"[green]Added:[/] {', '.join(added_keys)}")
    if (removed_keys := (set(base_environment) - set(new_environment))):
        logger.info(f"[red]Removed:[/] {', '.join(removed_keys)}")
    if (changed_keys := [
        key for key in new_environment if key in base_environment and new_environment[key] != base_environment[key]
    ]):
        logger.info(f"[blue]Changed:[/] {', '.join(changed_keys)}")


def display_compose_diff(base_compose: str, new_compose: str) -> None:
    """ Display a diff between a base and new compose file. """
    if not (lines := list(difflib.unified_diff(base_compose.splitlines(), new_compose.splitlines(), lineterm=""))):
        logger.info("Compose diff: Newlines only")
        return

    logger.info("Compose diff:")
    for line in lines[2:]:
        colour = "default"
        if line.startswith("+"):
            colour = "green"
        elif line.startswith("-"):
            colour = "red"

        logger.info(f"[{colour}]{line}[/]", extra={"highlighter": None})

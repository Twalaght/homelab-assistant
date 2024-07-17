
""" Helper class to interact with the portainer API and update stacks. """
import re
from typing import Any

import requests
from rich.console import Console

from homelab_assistant.config import Config

console = Console()


class PortainerHelper:
    """ Create a helper class to interact with a given portainer instance.

    Args:
        api_key (str): Portainer API key with permission to modify and deploy stacks.
        portainer_url (str): URL to Portainer instance to interact with.
    """

    def __init__(self, api_key: str, portainer_url: str) -> None:
        self.portainer_url = portainer_url
        self.session = requests.session()
        self.session.headers.update({"X-API-Key": api_key})

    def get_stacks(self) -> dict[str, dict[str, Any]]:
        """ Get data on all defined Portainer stacks.

        Returns:
            dict[str, dict[str, Any]]: Key-value pairs of stack names to Portainer stack information.
        """
        response = self.session.get(f"{self.portainer_url}/api/stacks")
        response.raise_for_status()
        return {stack["Name"]: stack for stack in response.json()}

    def export_config_from_stacks(self) -> dict[str, str]:
        """ Export a config file with environment information currently present in Portainer's stacks.

        Returns:
            dict[str, str]: Config file with Portainer's stack environment information.
        """
        output = {}
        for stack in self.get_stacks():
            if (stack_env := {env["name"]: env["value"].strip('"') for env in stack["Env"]}):
                output.setdefault(stack["Name"], {"environment": {}})
                output[stack["Name"]]["environment"] = stack_env

        return {"stacks": output}

    def get_stack_compose_file(self, stack_id: int) -> str | None:
        """ Get the compose file associated with a given stack ID.

        Args:
            stack_id (int): Stack ID to get the compose file for.

        Returns:
            str | None: Compose file data string, or None if it did not exist.
        """
        try:
            response = self.session.get(f"{self.portainer_url}/api/stacks/{stack_id}/file")
            response.raise_for_status()
            return response.json()["StackFileContent"]
        except requests.HTTPError:
            return None

    def get_git_compose_file(self, stack_name: str, config: Config) -> str | None:
        """ Get the compose file associated a stacks Git config.

        Args:
            stack_name (str): Name of the stack in config to retrieve compose file for.
            config (Config): Config object to fet Git config from.

        Returns:
            str | None: Compose file data string, or None if it did not exist.
        """
        stack_git_config = config.stacks.get(stack_name).git

        repository = config.git_default.repository or stack_git_config.repository
        branch = config.git_default.branch or stack_git_config.branch
        file_path = stack_git_config.file_path

        if not all((repository, branch, file_path)):
            return None

        # Create the URL to the raw GitHub compose file
        url = f"https://raw.githubusercontent.com/{repository.strip('/')}/{branch.strip('/')}/{file_path.strip('.')}"

        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.HTTPError:
            return None

        return response.text

    def get_defined_env_vars(self, compose_file: str) -> list[str]:
        """ Search a compose file for environment variable names which are defined.

        Args:
            compose_file (str): Compose file data string.

        Returns:
            list[str]: List of environment variable names defined in the compose file.
        """
        return [env_var.strip() for env_var in re.findall(r"\${(.*?)}", compose_file)]

    def generate_env_values_from_config(self, required_env_names: list[str],
                                        config: Config, stack_name: str) -> dict[str, str]:
        """ Generate environment variable key value pairs defined in config for a given stack.

        Args:
            required_env_names (list[str]): Environment variable names required by the compose file.
            config (Config): Config object to source common and stack specific environment variable values from.
            stack_name (str): Name of the stack to consider.

        Raises:
            ValueError: No value defined for a given environment variable.

        Returns:
            dict[str, str]: Key-value pairs of environment variable names to their values.
        """
        output = {}
        for env in required_env_names:
            if (
                (value := config.common_environment.get(env, None)) or
                (value := config.stacks.get(stack_name).environment.get(env, None))
            ):
                # Values are wrapped in double quotes to escape them in portainer properly
                output[env] = f'"{value}"'
            else:
                console.print(f"[red]WARNING[/red]: No value defined '{env}' in stack '{stack_name}'")
                raise ValueError(f"No value defined '{env}' in stack '{stack_name}'")

        return output

    def sync_stacks(self, config: Config, dry_run: bool) -> None:
        """ Sync Portainer stack environment variable values with values defined in config.

        Raises:
            NotImplementedError: New deployment feature not implemented.
            ValueError: Compose file not defined in Git or Portainer.

        Args:
            config (Config): Config to source common and stack specific environment variable values from.
            dry_run (bool): Preview changes without syncing if True.
        """
        portainer_stack_info = self.get_stacks()

        for stack_name, stack_config in config.stacks.items():
            # If the stack is not required to be synced, continue
            if not stack_config.sync:
                continue

            # TODO - Implement deployments without existing stacks
            if not (portainer_stack := portainer_stack_info.get(stack_name)):
                raise NotImplementedError("New deployments not currently supported")

            # Extract stack info from the Portainer response
            stack_id = portainer_stack["Id"]
            endpoint_id = portainer_stack["EndpointId"]

            # Fetch both the Git and Portainer compose files if they exist
            git_compose = self.get_git_compose_file(stack_name, config)
            portainer_compose = self.get_stack_compose_file(stack_id)
            if not any((git_compose, portainer_compose)):
                raise ValueError(f"Compose file not defined in Git or Portainer for stack '{stack_name}'")

            # Set the compose file and generate the required environment variables
            compose = git_compose or portainer_compose
            required_env_vars = self.get_defined_env_vars(compose)
            config_env = self.generate_env_values_from_config(required_env_vars, config, stack_name)

            # Check if config or compose file need updating
            portainer_env = {env["name"]: env["value"] for env in portainer_stack["Env"]}
            if (config_env == portainer_env) and (compose == portainer_compose):
                console.print(f"[blue]Nothing to do for[/blue] '{stack_name}'")
                continue

            # Add required environment variables and compose file to the update payload
            payload = {
                "env": [
                    {"name": name, "value": value} for name, value in config_env.items()
                ],
                "stackFileContent": compose,
            }

            if dry_run:
                console.print(f"Changes detected for '{stack_name}'")
                continue

            # Update the stack with the generated payload
            console.print(f"Updating {stack_name}... ", end="")
            deploy_url = (f"{self.portainer_url}/api/stacks/{stack_id}?endpointId={endpoint_id}")
            response = self.session.put(deploy_url, json=payload)
            response.raise_for_status()
            console.print("[green]done[/green]")

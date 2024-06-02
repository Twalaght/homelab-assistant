
""" Helper class to interact with the portainer API and update stacks. """
import re
from typing import Any

import requests
from rich.console import Console

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

    def get_stacks(self) -> list[dict[str, Any]]:
        """ Get data on all defined Portainer stacks.

        Returns:
            list[dict[str, Any]]: List of dictionaries containing Portainer stack information.
        """
        response = self.session.get(f"{self.portainer_url}/api/stacks")
        response.raise_for_status()
        return sorted(response.json(), key=lambda stack: stack["Name"])

    def get_stack_compose_file(self, stack_id: int) -> str:
        """ Get the compose file associated with a given stack ID.

        Args:
            stack_id (int): Stack ID to get the compose file for.

        Returns:
            str: Compose file data string.
        """
        response = self.session.get(f"{self.portainer_url}/api/stacks/{stack_id}/file")
        response.raise_for_status()
        return response.json()["StackFileContent"]

    def get_defined_env_vars(self, compose_file: str) -> list[str]:
        """ Search a compose file for environment variable names which are defined.

        Args:
            compose_file (str): Compose file data string.

        Returns:
            list[str]: List of environment variable names defined in the compose file.
        """
        return [env_var.strip() for env_var in re.findall(r"\${(.*?)}", compose_file)]

    def generate_env_values_from_config(self, required_env_names: list[str],
                                        config: dict[str, dict[str, str]], stack_name: str) -> dict[str, str]:
        """ Generate environment variable key value pairs defined in config for a given stack.

        Args:
            required_env_names (list[str]): Environment variable names required by the compose file.
            config (dict[str, dict[str, str]]): Config to source common and stack specific \
                                                environment variable values from.
            stack_name (str): Name of the stack to consider.

        Returns:
            dict[str, str]: Key-value pairs of environment variable names to their values.
        """
        output = {}
        for env in required_env_names:
            if (value := config["common"].get(env, None)) or (value := config["stacks"][stack_name].get(env, None)):
                # Values are wrapped in double quotes to escape them in portainer properly
                output[env] = f'"{value}"'
            else:
                console.print(f"[red]WARNING[/red]: No value defined '{env}' in stack '{stack_name}'")

        return output

    def export_config_from_stacks(self) -> dict[str, str]:
        """ Export a config file with environment information currently present in Portainer's stacks.

        Returns:
            dict[str, str]: Config file with Portainer's stack environment information.
        """
        output = {}
        for stack in self.get_stacks():
            if (stack_env := {env["name"]: env["value"].strip('"') for env in stack["Env"]}):
                output[stack["Name"]] = stack_env

        return output

    def sync_stack_envs(self, config: dict[str, dict[str, str]],
                        sync_file: bool = False, sync_git: bool = False) -> None:
        """ Sync Portainer stack environment variable values with values defined in config.

        Args:
            config (dict[str, dict[str, str]]): Config to source common and stack specific \
                                                environment variable values from.
            sync_file (bool, optional): Sync file based stacks. Defaults to False.
            sync_git (bool, optional): Sync Git based stacks. Defaults to False.
        """
        # Exit early if neither sync condition is specified
        if not sync_file and not sync_git:
            return

        for stack in self.get_stacks():
            # Extract key information from the given stack data
            stack_name = stack["Name"]
            stack_id = stack["Id"]
            stack_env = {env["name"]: env["value"] for env in stack["Env"]}
            endpoint_id = stack["EndpointId"]
            is_git_based = bool(stack["GitConfig"])

            if stack_name in config["stacks"]:
                # Skip the stack if the type does not match the sync criteria
                if (is_git_based and not sync_git) or (not is_git_based and not sync_file):
                    continue

                stack_compose = self.get_stack_compose_file(stack_id)
                required_env_vars = self.get_defined_env_vars(stack_compose)
                config_env = self.generate_env_values_from_config(required_env_vars, config, stack_name)

                if config_env == stack_env:
                    console.print(f"[blue]Nothing to do for[/blue] '{stack_name}'")
                    continue

                payload = {"env": [
                    {"name": name, "value": value} for name, value in config_env.items()
                ]}

                # Updates to file based stacks must supply a compose file,
                # so attach the associated compose file if required
                if not is_git_based:
                    payload["stackFileContent"] = stack_compose

                # Change the deploy URL depending on the stack's type
                deploy_url = (f"{self.portainer_url}/api/stacks/{stack_id}"
                              f"{'/git/redeploy' if is_git_based else ''}"
                              f"?endpointId={endpoint_id}")

                console.print(f"Updating {stack_name}... ", end="")
                response = self.session.put(deploy_url, json=payload)
                response.raise_for_status()
                console.print("[green]done[/green]")

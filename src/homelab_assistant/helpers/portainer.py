
""" Helper class to interact with the portainer API and update stacks. """
import re
from typing import Any, cast

import requests

from homelab_assistant.models.config import Config, GitDefault, Stack
from homelab_assistant.utils import logging

logger = logging.getLogger(__name__)


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

    def export_config_from_stacks(self) -> dict[str, dict[str, dict[str, str]]]:
        """ Export a config file with environment information currently present in Portainer's stacks.

        Returns:
            dict[str, dict[str, dict[str, str]]]: Stacks with Portainer's stack environment information.
        """
        output = {}
        for stack in self.get_stacks().values():
            if (stack_env := {env["name"]: env["value"].strip('"') for env in stack["Env"]}):
                output.setdefault(str(stack["Name"]), {"environment": {}})
                output[str(stack["Name"])]["environment"] = stack_env

        return output

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
        if not (stack_git_config := config.stacks.get(stack_name, Stack()).git):
            return None

        git_default = config.git_default or GitDefault()
        repository = git_default.repository or stack_git_config.repository
        branch = git_default.branch or stack_git_config.branch
        file_path = stack_git_config.file_path

        if not all((repository, branch, file_path)):
            logger.warning(f"Insufficient Git config to get '{stack_name}' compose:\n"
                           f"{repository=}\n{branch=}\n{file_path=}")
            return None

        # Create the URL to the raw GitHub compose file.
        repository = cast(str, repository)
        branch = cast(str, branch)
        file_path = cast(str, file_path)
        url = f"https://raw.githubusercontent.com/{repository.strip('/')}/{branch.strip('/')}/{file_path.strip('.')}"

        try:
            response = self.session.get(url)
            response.raise_for_status()
        except requests.HTTPError:
            logger.warning(f"HTTP error for '{url}'")
            return None

        return response.text

    def get_defined_env_vars(self, compose_file: str) -> list[str]:
        """ Search a compose file for environment variable names which are defined.

        Args:
            compose_file (str): Compose file data string.

        Returns:
            list[str]: List of environment variable names defined in the compose file.
        """
        return list({env_var.strip() for env_var in re.findall(r"\${(.*?)}", compose_file)})

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
            value = (config.common_environment.get(env, None) or
                     config.stacks.get(stack_name, Stack()).environment.get(env, None))

            # Values are wrapped in double quotes to escape them in portainer properly.
            output[env] = f'"{value}"' if value else None

        # Raise an error if any variables were not defined.
        if undefined := [name for name, value in output.items() if value is None]:
            undefined_str = ", ".join([f"'{name}'" for name in undefined])
            error_msg = f"No values defined for {undefined_str} in stack '{stack_name}'"
            logger.error(error_msg)
            raise ValueError(error_msg)

        return cast(dict[str, str], output)

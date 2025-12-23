
""" Helper class to interact with the portainer API and update stacks. """
import re
from typing import Any, cast

import requests
from fluffless.utils import logging

from homelab_assistant.models.config import Config, Endpoint, GitDefault, Stack

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
        self.endpoint_mapping: dict[int, str] = {}

    def map_endpoints(self) -> dict[int, str]:
        """ Generate a mapping of endpoint IDs to their associated friendly names. """
        response = self.session.get(f"{self.portainer_url}/api/endpoints")
        response.raise_for_status()

        return {endpoint["Id"]: endpoint["Name"] for endpoint in response.json()}

    def get_stacks(self) -> dict[str, dict[str, dict[str, Any]]]:
        """ Get data on all defined Portainer stacks, in all endpoints.

        Returns:
            dict[str, dict[str, dict[str, Any]]]: Endpoint friendly name grouped key-value pairs of \
                                                  stack names to Portainer stack information.
        """
        if not self.endpoint_mapping:
            self.endpoint_mapping = self.map_endpoints()

        response = self.session.get(f"{self.portainer_url}/api/stacks")
        response.raise_for_status()

        endpoint_grouped_stack_info = {
            self.endpoint_mapping[endpoint]: {} for endpoint in
            {stack["EndpointId"] for stack in response.json()}
            if endpoint in self.endpoint_mapping
        }

        for stack in response.json():
            if (endpoint := stack["EndpointId"]) not in self.endpoint_mapping:
                continue

            friendly_endpoint_name = self.endpoint_mapping[endpoint]
            endpoint_grouped_stack_info[friendly_endpoint_name][stack["Name"]] = stack

        return endpoint_grouped_stack_info

    def update_stack(self, endpoint_id: int, stack_id: int, compose: str, environment: dict[str, str]) -> None:
        """ Update a stack specified by endpoint and stack ID with a given compose and environment.

        Args:
            endpoint_id (int): Endpoint the stack exists on.
            stack_id (int): ID of the stack to update.
            compose (str): Compose file content.
            environment (dict[str, str]): Key value pairs of environment variable names to values.
        """
        # Add required environment variables and compose file to the update payload.
        payload = {
            "env": [
                {"name": name, "value": value} for name, value in environment.items()
            ],
            "stackFileContent": compose,
        }

        # Update the stack with the generated payload.
        response = self.session.put(
            url=f"{self.portainer_url}/api/stacks/{stack_id}",
            params={"endpointId": endpoint_id},
            json=payload,
        )
        response.raise_for_status()

        return response.json()

    def export_stack_env_from_endpoints(self) -> dict[str, Endpoint]:
        """ Export a config file of all currently present stack environment information in all endpoints. """
        output = {}
        for endpoint_name, stacks in self.get_stacks().items():
            output[endpoint_name] = Endpoint(
                stacks={
                    stack_name: Stack(
                        environment={
                            env.get("name", ""): env.get("value", "").strip('"')
                            for env in stack_data.get("Env", [])
                        },
                        sync=False,
                    )
                    for stack_name, stack_data in stacks.items()
                },
            )

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

    def get_git_compose_file(self, endpoint_name: str, stack_name: str, config: Config) -> str | None:
        """ Get the compose file associated a stacks Git config.

        Args:
            endpoint_name (str): Name of the endpoint environment to inspect stacks of.
            stack_name (str): Name of the stack in config to retrieve compose file for.
            config (Config): Config object to fet Git config from.

        Returns:
            str | None: Compose file data string, or None if it did not exist.
        """
        if not (stack_git_config := config.endpoints[endpoint_name].stacks.get(stack_name, Stack()).git):
            return None

        git_default = config.git_default or GitDefault()
        repository = stack_git_config.repository or git_default.repository
        branch = stack_git_config.branch or git_default.branch
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
                                        config: Config, endpoint_name: str, stack_name: str) -> dict[str, str]:
        """ Generate environment variable key value pairs defined in config for a given stack.

        Args:
            required_env_names (list[str]): Environment variable names required by the compose file.
            config (Config): Config object to source common and stack specific environment variable values from.
            endpoint_name (str): Name of the endpoint environment to inspect stacks of.
            stack_name (str): Name of the stack to consider.

        Raises:
            ValueError: No value defined for a given environment variable.

        Returns:
            dict[str, str]: Key-value pairs of environment variable names to their values.
        """
        output = {}
        for env in required_env_names:
            value = (config.common_environment.get(env, None) or
                     config.endpoints[endpoint_name].stacks.get(stack_name, Stack()).environment.get(env, None))

            # Values are wrapped in double quotes to escape them in portainer properly.
            output[env] = f'"{value}"' if value else None

        # Raise an error if any variables were not defined.
        if undefined := [name for name, value in output.items() if value is None]:
            undefined_str = ", ".join([f"'{name}'" for name in undefined])
            error_msg = f"No values defined for {undefined_str} in stack '{stack_name}'"
            logger.error(error_msg)
            raise ValueError(error_msg)

        return cast(dict[str, str], output)

""" Dataclass definitions for main application config object. """
from fluffless.models.base_model import BaseModel
from fluffless.utils import logging

logger = logging.getLogger(__name__)


class GitDefault(BaseModel):
    """ Model definition of default Git config. """

    repository: str | None = None
    branch:     str | None = None


class Git(GitDefault):
    """ Model definition of a specific stack's Git config. """

    file_path: str | None = None


class Portainer(BaseModel):
    """ Model definition of Portainer config. """

    api_key: str
    url:     str


class Stack(BaseModel):
    """ Model definition of main stack config object. """

    environment: dict[str, str] = {}
    git:         Git | None = None
    sync:        bool = True


class Endpoint(BaseModel):
    """ Model definition of a Portainer endpoint. """

    stacks: dict[str, Stack] = {}


class Config(BaseModel):
    """ Model definition of main config object. """

    portainer:          Portainer
    git_default:        GitDefault | None = None
    endpoints:          dict[str, Endpoint] = {}
    common_environment: dict[str, str] = {}

    def check(self) -> None:
        """ Health check the config object and log and potential issues and warnings. """

        def check_env_vars(environment_variables: dict[str, str], logging_prefix: str) -> None:
            for name, value in environment_variables.items():
                if name.upper() != name:
                    logger.warning(f"{logging_prefix} variable '{name}' is not full caps")

                if not value:
                    logger.warning(f"Common environment variable '{name}' is set to a blank value")

        all_stack_env_vars = {}
        check_env_vars(self.common_environment, "Common environment")
        for full_stack_data in self.endpoints.values():
            for stack_name, stack_data in full_stack_data.stacks.items():
                check_env_vars(stack_data.environment, f"Stack '{stack_name}'")

                # Keep a dictionary of all defined environment variables in all stacks.
                for env_name, env_value in stack_data.environment.items():
                    all_stack_env_vars.setdefault(env_name, []).append(env_value)

        # Suggest potential comment environment variables, if they were defined multiple times with the same value.
        for env_name, env_values in all_stack_env_vars.items():
            if len(env_values) >= 2 and len(set(env_values)) == 1:
                logger.info(f"Consider making environment variable '{env_name}' common")

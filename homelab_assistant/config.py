""" Dataclass definitions for main application config object. """
from attrs import define, field


@define
class GitDefault:
    """ Dataclass definition of default Git config. """

    repository:           str | None = None
    branch:               str | None = None


@define
class Git(GitDefault):
    """ Dataclass definition of a stack's Git config. """

    file_path:            str | None = None


@define
class Portainer:
    """ Dataclass definition of Portainer config. """

    api_key: str | None = None
    url:     str | None = None


@define
class Config:
    """ Dataclass definition of main config object. """

    @define
    class Stack:
        """ Dataclass definition of main stack config object. """

        environment: dict[str, str] = field(factory=dict)
        git:         Git = field(factory=Git)
        sync:        bool = False

    git_default:        GitDefault = field(factory=GitDefault)
    portainer:          Portainer = field(factory=Portainer)
    stacks:             dict[str, Stack] = field(factory=dict)
    common_environment: dict[str, str] = field(factory=dict)

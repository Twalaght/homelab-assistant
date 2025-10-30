""" Runner module to provide entrypoint decorator functions for CLI interface.

Example usage of CLI entrypoints: ::

    _BASE_PARSER = cli.create_subparser(command="grouped_parsers", has_subparsers=True)
    _PARSER = _BASE_PARSER.add_parser("awoo", parents=[cli.base_leaf_parser()])

    @entrypoint(_PARSER)
    def awoo() -> None:
        print("Awoo!")

    cli.run(parse_args(), Config())
"""
import argparse
from typing import Any, Callable

from rich_argparse import _lazy_rich, RichHelpFormatter

from homelab_assistant.models.config import Config


class RawRichHelpFormatter(RichHelpFormatter):
    """ Custom argparse formatter class to use Rich colouring, and preserve raw formatting. """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.styles |= {
            "argparse.todo": "red",
            "argparse.quote": "green",
            "argparse.menu_item": "cyan",
            "argparse.default": "italic dark_cyan",
        }

        self.highlights.extend([
            r"(?P<todo>todo|TODO)",
            r"(?P<quote>'.*?')",
            r"\n\s+(?P<menu_item>\w+):",
        ])

    def _rich_split_lines(self, text: _lazy_rich.Text, width: int) -> _lazy_rich.Lines:
        """ Define a custom line split method to preserve raw text formatting when displaying help strings. """
        text = text.copy()
        text.expand_tabs(8)  # Textwrap expands tabs first.
        return text.wrap(self.console, width)

    def _get_help_string(self, action: argparse.Action) -> str | None:
        """ Add default help string arguments for actions which require them. """
        # Do not add default argument strings for specific argparse actions.
        if tuple(action.option_strings) in (
            ("-v", "--verbose"),              # Standard verbosity flag
        ):
            return super()._get_help_string(action)

        if (
            "%(default)" not in (action.help or "")  # Do not add default strings if they were already present.
            and action.default != "==SUPPRESS=="     # Default value for the `--help` argument.
            and action.default is not None           # Do not add default strings for null defaults.
        ):
            # Argparse `nargs` may take the values ("?", "*", "+"). The value "+" requires one or more value
            # as input, and as such does not take a default. Both "?" and "*" permit no input, and thus are
            # able to take default arguments, and should have their help strings modified.
            defaulting_nargs = ("?", "*")
            if action.option_strings or action.nargs in defaulting_nargs:
                # Do not add a leading space if the default is intentionally on a new line.
                padding = " " if not (help_str := action.help or "").endswith("\n") else ""
                action.help = f"{help_str}{padding}Defaults to %(default)s."

        return super()._get_help_string(action)


# Apply this formatter across all parsers (root AND subparsers).
FORMATTER_CLASS = RawRichHelpFormatter

__ROOT_PARSER = argparse.ArgumentParser(formatter_class=FORMATTER_CLASS, add_help=False)
__ROOT_PARSER.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                           help="Show this help message and exit.")
__ROOT_SUBPARSERS = __ROOT_PARSER.add_subparsers(required=True)
__ROOT_PARSER.set_defaults(_entry_func=None)
EntryFunc = Callable[[argparse.Namespace, Config], Any]


def _parser_template(is_leaf: bool) -> argparse.ArgumentParser:
    """ Template parser to add standard arguments to all parsers.

    Allows standardised configuration functionality across all leaf parsers, such as logging verbosity, config file
    locations, and logging output file.

    For non-leaf parsers, only the --help command is added.

    Args:
        is_leaf (bool): Whether the parser is a command to be invoked directly (a leaf) or \
                        has its own set of subparsers (not a leaf).

    Returns:
        argparse.ArgumentParser: A parser object suitable to use as a parent parser, to inherit common arguments.
    """
    parser = argparse.ArgumentParser(description="PARENT PARSER - NOT TO BE USED DIRECTLY",
                                     add_help=False, formatter_class=FORMATTER_CLASS)
    parser.add_argument("-h", "--help", action="help", default=argparse.SUPPRESS,
                        help="Show this help message and exit.")
    if is_leaf:
        parser.add_argument("-v", "--verbose", action="count", default=0,
                            help="Increase verbosity of displayed logger output.")
    return parser


def add_parser(name: str, subparsers: argparse._SubParsersAction | None = None, is_leaf: bool = True,
               **kwargs) -> argparse.ArgumentParser:
    """ Create a parser under a given subparsers group, or the root subparsers group if one is not provided.

    If a description was not provided for the subparser, uses the help string as a description.

    Args:
        name (str): The name of the subcommand, i.e. the CLI verb to invoke it.
        subparsers (argparse._SubParsersAction | None, optional): Subparsers group to add the new parser to. \
                                                                  Defaults to None, where the root subparser \
                                                                  group will be used by default.
        is_leaf (bool, optional): Whether the parser is a command to be invoked directly (a leaf) or \
                                  has its own set of subparsers (not a leaf). Defaults to True.
        **kwargs: Additional keyword arguments to pass to `add_parser()`.

    Returns:
        argparse.ArgumentParser: The created parser.
    """
    add_parser_kwargs = {
        "parents": [_parser_template(is_leaf=is_leaf)],
        "formatter_class": FORMATTER_CLASS,
        "description": kwargs.get("description") or kwargs.get("help"),
    }
    add_parser_kwargs.update(kwargs)
    # TODO - `ty` current does not support handling `**kwargs`.
    return (
        subparsers or __ROOT_SUBPARSERS
    ).add_parser(name, **add_parser_kwargs, add_help=False)  # type: ignore[invalid-argument-type]


def run(args: argparse.Namespace) -> None:
    """ Invoke the entry point function selected by the user."""
    if args._entry_func:
        args._entry_func(args)
    else:
        __ROOT_PARSER.print_help()


def entrypoint(parser: argparse.ArgumentParser) -> Callable:
    """ Decorate a function or class method, declaring it the default entrypoint for the given parser.

    Args:
        parser (argparse.ArgumentParser): The (sub)parser responsible for this class method.

    Returns:
        Callable: A modified decorator function with with variable scope access to the provided parser.
    """
    def entrypoint_decorator(entry_func: EntryFunc) -> EntryFunc:
        """ Set `entry_func` as the default function for the specified parser.

        As this decorator has arguments, an additional decoration function layer must be created.

        Args:
            entry_func (EntryFunc): The function to be declared as an entry point.

        Returns:
            EntryFunc: The same function unchanged, now registered as the default entry point
                       function for the parser given above in `entrypoint()`.
        """
        parser.set_defaults(_entry_func=entry_func)

        # The behaviour of entry_func does not need to be modified, so it can simply be returned.
        return entry_func

    return entrypoint_decorator

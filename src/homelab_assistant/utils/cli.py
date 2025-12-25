""" Extension on the base parser provided by `fluffless`. """
import argparse

from fluffless.utils.cli import base_parser


def leaf_parser() -> argparse.ArgumentParser:
    """ Leaf parser with config file argument added. """
    parser = base_parser(is_leaf=True)
    parser.add_argument("config_file", help="YAML file to source configuration data from.")
    return parser

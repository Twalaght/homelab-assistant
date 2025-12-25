""" Runner entrypoint for HomeLab Assistant. """
from pathlib import Path

import yaml
from fluffless.utils import cli, logging

from homelab_assistant import runners
from homelab_assistant.models.config import Config

logger = logging.getLogger(__name__)


def main() -> None:
    """ Entrypoint runner. """
    cli.import_package_modules(runners)
    args = cli.parse_args()

    logging.setup_logger(
        verbosity=args.verbose,
        modules=["homelab_assistant"],
    )

    # TODO - If file doesn't exist

    # Load config from the provided config file.
    with Path(args.config_file).open() as f:
        config_data = yaml.safe_load(f)
        config = Config(**config_data)
        config.check()

    cli.run(args, config)


if __name__ == "__main__":
    main()

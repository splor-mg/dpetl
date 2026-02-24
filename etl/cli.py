import argparse

from .extract.cli import create_extract_subcommands

def build_parser():
    parser = argparse.ArgumentParser(
        prog="etl",
        description="ETL Command Line Interface",
    )

    parser.add_argument(
        '--descriptor',
        '-d',
        default='datapackage.yaml',
        help='Path to a datapackage.yaml file (default: datapackage.yaml).',
    )

    subparsers = parser.add_subparsers(
        title="commands",
        dest="command",
        required=True,
    )

    create_extract_subcommands(subparsers)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)

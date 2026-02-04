from .email_cli import email


def create_extract_subcommands(subparsers):

    parser = subparsers.add_parser('extract', help='Simplified some ETL extract operations.')

    subparsers = parser.add_subparsers(
        title="extract commands",
        dest="extract_command",
        required=True,
    )

    email(subparsers)

    return subparsers

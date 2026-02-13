# from .email_cli import email
from etl.helpers import resources_iteration

def create_extract_subcommands(subparsers):

    # parser = subparsers.add_parser('extract', help='Simplified some ETL extract operations.')

    # subparsers = parser.add_subparsers(
    #     title="extract commands",
    #     dest="extract_command",
    #     required=True,
    # )

    # email(subparsers)

    # return subparsers

    parser = subparsers.add_parser('extract', help='Simplified some ETL extract operations.')

    parser.set_defaults(func=handle_command)

    return parser

def handle_command(args):

    resources_iteration(**vars(args))

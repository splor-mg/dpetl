from dpetl.helpers.iterator import descriptor_iteration


def create_load_subcommands(subparsers):

    parser = subparsers.add_parser(
        'load', help='Simplified some ETL load operations.'
    )

    parser.set_defaults(func=handle_command)

    return parser


def handle_command(args):

    descriptor_iteration(operation='load', **vars(args))

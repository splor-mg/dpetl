from dpetl.helpers.iterator import descriptor_iteration


def create_transform_subcommands(subparsers):

    parser = subparsers.add_parser(
        'transform', help='Simplified some ETL transform operations.'
    )

    parser.set_defaults(func=handle_command)

    return parser


def handle_command(args):

    descriptor_iteration(operation='transform', **vars(args))

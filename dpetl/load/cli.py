from dpetl.helpers.iterator import descriptor_iteration


def create_load_subcommands(subparsers):

    parser = subparsers.add_parser(
        'load', help='Simplified some ETL load operations.'
    )

    parser.add_argument(
        '--private',
        '-p',
        action='store_true',
        help='Create repositories as private instead of public.',
    )

    parser.add_argument(
        '--org',
        '-o',
        action='store_true',
        help='Indicates that the repositories should be created under an organization.',
    )

    parser.set_defaults(func=handle_command)

    return parser


def handle_command(args):

    descriptor_iteration(operation='load', **vars(args))

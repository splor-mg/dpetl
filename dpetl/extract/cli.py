from dpetl.helpers.iterator import resources_iteration


def create_extract_subcommands(subparsers):

    parser = subparsers.add_parser(
        'extract', help='Simplified some ETL extract operations.'
    )

    parser.add_argument(
        '--today-email',
        '-t',
        action='store_true',
        help='Extract e-mails received in the same date the command runs.',
    )

    parser.add_argument(
        '--add-package-name',
        '-a',
        action='store_true',
        help='Add the package name to the subject property. This will search for a subejct pattern like {package_name}_{resource_name} instead of just {resource_name}.',
    )

    parser.set_defaults(func=handle_command)

    return parser


def handle_command(args):

    resources_iteration(**vars(args))


def gmail(subparsers):
    new_cmd = subparsers.add_parser('gmail',
        aliases=['g',],
        help='Extract resources from gmail.'
    )
    # new_cmd.add_argument(
    #     'name',
    #     help='Name of the new orphan branch to create.',
    # )
    # new_cmd.add_argument(
    #     '--readme',
    #     '-r',
    #     action='store_true',
    #     help='Add a README.md file to the new orphan branch created.',
    # )
    new_cmd.set_defaults(func=handle_command)

def handle_command(args):

    print('Extracting from Gmail...')

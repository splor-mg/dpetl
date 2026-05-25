import pytest

from dpetl import cli


def test_extract_uses_default_descriptor():
    args = cli.build_parser().parse_args(['extract'])

    assert args.command == 'extract'
    assert args.descriptor == 'datapackage.yaml'
    assert args.today_email is False
    assert args.add_package_name is False


def test_descriptor_long_flag_is_parsed_before_command():
    args = cli.build_parser().parse_args(
        ['--descriptor', 'custom.yaml', 'extract']
    )

    assert args.command == 'extract'
    assert args.descriptor == 'custom.yaml'


def test_descriptor_short_flag_is_parsed_before_command():
    args = cli.build_parser().parse_args(['-d', 'custom.yaml', 'extract'])

    assert args.command == 'extract'
    assert args.descriptor == 'custom.yaml'


def test_descriptor_after_command_is_invalid():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(['extract', '--descriptor', 'custom.yaml'])


def test_extract_email_flags_are_parsed():
    args = cli.build_parser().parse_args(
        ['extract', '--today-email', '--add-package-name']
    )

    assert args.today_email is True
    assert args.add_package_name is True


def test_command_is_required():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args([])

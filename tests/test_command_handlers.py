from argparse import Namespace

from dpetl.extract import cli as extract_cli
from dpetl.load import cli as load_cli
from dpetl.transform import cli as transform_cli


def test_extract_handle_command_calls_descriptor_iteration(monkeypatch):
    calls = []

    def fake_descriptor_iteration(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        extract_cli,
        'descriptor_iteration',
        fake_descriptor_iteration,
    )

    args = Namespace(
        command='extract',
        descriptor='custom.yaml',
        today_email=True,
        add_package_name=False,
        func=extract_cli.handle_command,
    )

    extract_cli.handle_command(args)

    assert calls == [
        {
            'operation': 'extract',
            'command': 'extract',
            'descriptor': 'custom.yaml',
            'today_email': True,
            'add_package_name': False,
            'func': extract_cli.handle_command,
        }
    ]


def test_transform_handle_command_calls_descriptor_iteration(monkeypatch):
    calls = []

    def fake_descriptor_iteration(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        transform_cli,
        'descriptor_iteration',
        fake_descriptor_iteration,
    )

    args = Namespace(
        command='transform',
        descriptor='custom.yaml',
        func=transform_cli.handle_command,
    )

    transform_cli.handle_command(args)

    assert calls == [
        {
            'operation': 'transform',
            'command': 'transform',
            'descriptor': 'custom.yaml',
            'func': transform_cli.handle_command,
        }
    ]


def test_load_handle_command_calls_descriptor_iteration(monkeypatch):
    calls = []

    def fake_descriptor_iteration(**kwargs):
        calls.append(kwargs)

    monkeypatch.setattr(
        load_cli,
        'descriptor_iteration',
        fake_descriptor_iteration,
    )

    args = Namespace(
        command='load',
        descriptor='custom.yaml',
        func=load_cli.handle_command,
    )

    load_cli.handle_command(args)

    assert calls == [
        {
            'operation': 'load',
            'command': 'load',
            'descriptor': 'custom.yaml',
            'func': load_cli.handle_command,
        }
    ]

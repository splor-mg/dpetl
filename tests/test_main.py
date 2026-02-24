from dpetl import cli


def test_hello():
    assert cli.hello() == 'Hello, world!'

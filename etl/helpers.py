from frictionless import Package


def resources_iteration(descriptor=None, package=None, function=None):
    """
    Iterate on resources from a package descriptor or a package object and apply a function to each resource.
    """
    if descriptor:
        package = Package(descriptor)

    if not package:
        raise ValueError('Either descriptor or package must be provided.')

    for resource in package.resources:
        function(resource)

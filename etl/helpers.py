from frictionless import Package
from .extract import email


def resources_iteration(**kwargs):
    """
    Iterate on resources from a package descriptor or a package object and apply a function to each resource.
    """
    descriptor = kwargs.get('descriptor')
    if descriptor:
        package = Package(descriptor)

    # TODO: As the package instaciation is here, read what extraction_mode is in the descriptor and decide which function to apply, instead of receiving it as an argument. Would it be useful?
    for resource in package.resources:
        if resource.custom['extract_info']['mode'] == 'email':
            email.extract_email(resource, **kwargs)

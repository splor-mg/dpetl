from frictionless import Package
from .extract import email
from .extract import api

def resources_iteration(**kwargs):
    """
    Iterate on resources from a package descriptor or a package object and apply a function to each resource.
    """
    descriptor = kwargs.get('descriptor')
    if descriptor:
        package = Package(descriptor)

    for resource in package.resources:
        if resource.custom['extract_info']['mode'] == 'email':
            email.extract_email(resource, **kwargs)
        elif resource.custom['extract_info']['mode'] == 'api':
            api.extract_api(resource, **kwargs)

from rest_framework.permissions import DjangoModelPermissions


class EpiphanChannelPermissions(DjangoModelPermissions):
    perms_map = {
        'GET': [],
        'OPTIONS': [],
        'HEAD': [],
        'POST': ['%(app_label)s.add_%(model_name)s'],
        'PUT': ['%(app_label)s.change_%(model_name)s'],
        'PATCH': ['%(app_label)s.change_%(model_name)s'],
        'DELETE': ['%(app_label)s.delete_%(model_name)s'],
        'START': ['%(app_label)s.change_%(model_name)s'],
        'STOP': ['%(app_label)s.change_%(model_name)s'],
    }

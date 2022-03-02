from outpost.django.api.permissions import ExtendedDjangoModelPermissions


class EpiphanChannelPermissions(ExtendedDjangoModelPermissions):
    perms_map = ExtendedDjangoModelPermissions.perms_map | {
        "START": ["%(app_label)s.change_%(model_name)s"],
        "STOP": ["%(app_label)s.change_%(model_name)s"],
    }

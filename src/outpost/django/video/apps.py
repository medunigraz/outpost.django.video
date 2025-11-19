from django.apps import AppConfig
from django.db.models.signals import post_save
from django.utils.translation import gettext_lazy as _


class DefaultConfig(AppConfig):
    name = __package__
    verbose_name = _("Video")

    def ready(self):
        from .signals import RecordingPermissionReceiver

        post_save.connect(
            RecordingPermissionReceiver.user, sender="guardian.UserObjectPermission"
        )
        post_save.connect(
            RecordingPermissionReceiver.group, sender="guardian.GroupObjectPermission"
        )

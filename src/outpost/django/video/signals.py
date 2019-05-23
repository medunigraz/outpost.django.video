from .models import Recording


class RecordingPermissionReceiver():

    @classmethod
    def assign(cls, obj, created, entity):
        if not created:
            return
        if not obj.content_type.model_class() == Recording:
            return
        perm = obj.permission.codename.replace(
            '_recording',
            '_recordingasset'
        )
        for ra in obj.content_object.recordingasset_set.all():
            assign_perm(
                perm,
                entity,
                ra
            )

    @classmethod
    def user(cls, sender, instance, created, **kwargs):
        cls.assign(instance, created, instance.user)

    @classmethod
    def group(cls, sender, instance, created, **kwargs):
        cls.assign(instance, created, instance.group)

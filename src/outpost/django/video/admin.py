from django.contrib import admin

from outpost.django.base.admin import NotificationInlineAdmin

from . import models


class EpiphanRecordingInlineAdmin(admin.TabularInline):
    model = models.EpiphanRecording


class RecordingAssetInlineAdmin(admin.TabularInline):
    model = models.RecordingAsset


class EpiphanChannelInlineAdmin(admin.TabularInline):
    model = models.EpiphanChannel


class EpiphanSourceInlineAdmin(admin.TabularInline):
    model = models.EpiphanSource


@admin.register(models.Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("__str__", "fingerprint", "active")
    list_filter = ()
    search_fields = ("hostname", "port")
    readonly_fields = ("fingerprint",)

    def fingerprint(self, obj):
        return "<code>{}</code>".format(obj.fingerprint())

    fingerprint.short_description = u"SSH host key fingerprint"
    fingerprint.allow_tags = True


@admin.register(models.Epiphan)
class EpiphanAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "hostname",
        "server",
        "fingerprint",
        "online",
        "provision",
    )
    list_filter = ("server", "online", "provision")
    search_fields = ("name", "hostname", "fingerprint")
    readonly_fields = ("fingerprint", "private_key")
    inlines = (
        EpiphanChannelInlineAdmin,
        EpiphanSourceInlineAdmin,
        EpiphanRecordingInlineAdmin,
        NotificationInlineAdmin,
    )

    def fingerprint(self, obj):
        return "<code>{}</code>".format(obj.fingerprint())

    fingerprint.short_description = u"SSH public key fingerprint"
    fingerprint.allow_tags = True

    def private_key(self, obj):
        return "<pre>{}</pre>".format(obj.private_key())

    private_key.short_description = u"SSH private key"
    private_key.allow_tags = True


# class EventInlineAdmin(admin.TabularInline):
#     model = models.Event
#
#
# @admin.register(models.Series)
# class SeriesAdmin(admin.ModelAdmin):
#     inlines = (
#             EventInlineAdmin,
#     )
#
#
# @admin.register(models.Event)
# class EventAdmin(admin.ModelAdmin):
#     pass


@admin.register(models.Recording)
class RecordingAdmin(admin.ModelAdmin):
    list_display = ("pk", "recorder", "created")
    date_hierarchy = "created"
    list_filter = ("recorder",)
    inlines = (RecordingAssetInlineAdmin,)


@admin.register(models.PanasonicCamera)
class PanasonicCameraAdmin(admin.ModelAdmin):
    pass


@admin.register(models.TranscribeLanguage)
class TranscribeLanguageAdmin(admin.ModelAdmin):
    pass

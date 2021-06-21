from django.contrib import admin
from django.utils.translation import ugettext_lazy as _
from outpost.django.base.admin import NotificationInlineAdmin

from . import models


@admin.register(models.EpiphanRecording)
class EpiphanRecordingAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "recorder",
        "channel",
        "start",
        "end",
        "presenter",
        "course",
        "title",
        "ready",
    )
    list_filter = ("recorder", "ready")
    search_fields = ("presenter", "course", "title")


class RecordingAssetInlineAdmin(admin.TabularInline):
    model = models.RecordingAsset


class EpiphanChannelInlineAdmin(admin.TabularInline):
    model = models.EpiphanChannel


class EpiphanSourceInlineAdmin(admin.TabularInline):
    model = models.EpiphanSource


@admin.register(models.Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("__str__", "fingerprint", "enabled")
    list_filter = ("enabled",)
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


@admin.register(models.LivePortal)
class LivePortalAdmin(admin.ModelAdmin):
    pass


@admin.register(models.LiveChannel)
class LiveChannelAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "name",
        "enabled",
    )
    list_filter = ("enabled",)


@admin.register(models.LiveDeliveryServer)
class LiveDeliveryServerAdmin(admin.ModelAdmin):
    list_display = (
        "base",
        "online",
    )
    list_filter = ("online",)


class LiveStreamVariantRequirementInline(admin.TabularInline):
    model = models.LiveStreamVariantRequirement


@admin.register(models.LiveStreamVariant)
class LiveStreamVariantAdmin(admin.ModelAdmin):
    list_display = (
        "height",
        "preset",
        "profile",
        "video",
        "audio",
    )
    inlines = (
        LiveStreamVariantRequirementInline,
    )


@admin.register(models.LiveTemplate)
class LiveTemplateAdmin(admin.ModelAdmin):
    pass


class LiveTemplateStreamInline(admin.TabularInline):
    model = models.LiveTemplateStream


@admin.register(models.LiveTemplateScene)
class LiveTemplateSceneAdmin(admin.ModelAdmin):
    list_filter = ("template",)
    search_fields = ("name",)
    inlines = (
        LiveTemplateStreamInline,
    )


class LiveStreamInline(admin.TabularInline):
    model = models.LiveStream


class LiveViewerInline(admin.TabularInline):
    model = models.LiveViewer


@admin.register(models.LiveEvent)
class LiveEventAdmin(admin.ModelAdmin):
    list_display = (
        "pk",
        "channel",
        "title",
        "begin",
        "end",
        "public",
    )
    list_filter = ("channel", "public", "begin", "end")
    search_fields = ("title", "description")
    inlines = (
        LiveStreamInline,
        LiveViewerInline
    )
    actions = ("start", "stop")

    def start(self, request, queryset):
        for e in queryset.all():
            e.start()
    start.short_description = _('Start selected live events')

    def stop(self, request, queryset):
        for e in queryset.all():
            e.stop()
    stop.short_description = _('Stop selected live events')


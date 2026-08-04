from django.conf.urls import url
from django.contrib import (
    admin,
    messages,
)
from django.http import HttpResponse
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import ngettext
from django.utils.translation import ugettext_lazy as _
from guardian.shortcuts import get_objects_for_user
from ordered_model.admin import OrderedModelAdmin
from outpost.django.base.admin import NotificationInlineAdmin
from outpost.django.base.guardian import (
    GuardedModelAdminFilterMixin,
    GuardedModelAdminMixin,
    GuardedModelAdminPermissionMixin,
    GuardedModelAdminSaveMixin,
)
from polymorphic.admin import (
    PolymorphicChildModelAdmin,
    PolymorphicChildModelFilter,
    PolymorphicParentModelAdmin,
)

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

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        view = f"{qs.model._meta.app_label}.view_recorder"
        change = f"{qs.model._meta.app_label}.change_recorder"
        epiphans = get_objects_for_user(
            request.user,
            (view, change),
            models.Epiphan.objects.all(),
            accept_global_perms=True,
        )
        return qs.filter(recorder__in=epiphans)


class RecordingAssetInlineAdmin(admin.TabularInline):
    model = models.RecordingAsset


class EpiphanChannelInlineAdmin(admin.TabularInline):
    model = models.EpiphanChannel


class EpiphanSourceInlineAdmin(admin.TabularInline):
    model = models.EpiphanSource


class EpiphanMediaInlineAdmin(admin.TabularInline):
    model = models.EpiphanMedia
    readonly_fields = ("name",)


class EpiphanInputInlineAdmin(admin.TabularInline):
    model = models.EpiphanInput


@admin.register(models.Server)
class ServerAdmin(admin.ModelAdmin):
    list_display = ("__str__", "fingerprint", "enabled")
    list_filter = ("enabled",)
    search_fields = ("hostname", "port")
    readonly_fields = ("fingerprint",)

    def fingerprint(self, obj):
        return mark_safe("<code>{}</code>".format(obj.fingerprint()))

    fingerprint.short_description = "SSH host key fingerprint"


@admin.register(models.Epiphan)
class EpiphanAdmin(
    GuardedModelAdminFilterMixin,
    GuardedModelAdminSaveMixin,
    GuardedModelAdminPermissionMixin,
    GuardedModelAdminMixin,
    admin.ModelAdmin,
):
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
        EpiphanMediaInlineAdmin,
        EpiphanInputInlineAdmin,
        NotificationInlineAdmin,
    )
    base_model = models.Recorder

    def fingerprint(self, obj):
        return mark_safe("<code>{}</code>".format(obj.fingerprint()))

    fingerprint.short_description = "SSH public key fingerprint"

    def private_key(self, obj):
        return mark_safe("<pre>{}</pre>".format(obj.private_key()))

    private_key.short_description = "SSH private key"


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
class LiveChannelAdmin(OrderedModelAdmin):
    list_display = ("name", "pk", "enabled", "move_up_down_links")
    list_filter = ("enabled",)


class LiveDeliveryServerNetworkInline(admin.TabularInline):
    model = models.LiveDeliveryServerNetwork


class LiveDeliveryServerCountryInline(admin.TabularInline):
    model = models.LiveDeliveryServerCountry


@admin.register(models.LiveDeliveryServer)
class LiveDeliveryServerAdmin(admin.ModelAdmin):
    list_display = ("base", "enabled", "online")
    list_filter = ("enabled", "online")
    inlines = (LiveDeliveryServerNetworkInline, LiveDeliveryServerCountryInline)


class LiveStreamVariantRequirementInline(admin.TabularInline):
    model = models.LiveStreamVariantRequirement


@admin.register(models.LiveStreamVariant)
class LiveStreamVariantAdmin(admin.ModelAdmin):
    list_display = ("height", "preset", "profile", "video", "audio")
    inlines = (LiveStreamVariantRequirementInline,)


@admin.register(models.LiveTemplate)
class LiveTemplateAdmin(admin.ModelAdmin):
    pass


class PushServerProtocolInline(admin.TabularInline):
    model = models.PushServerProtocol


@admin.register(models.PushServer)
class PushServerAdmin(admin.ModelAdmin):
    list_display = ("hostname", "url", "enabled")
    list_filter = ("enabled",)
    inlines = (PushServerProtocolInline,)
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "hostname",
                    "enabled",
                    "url",
                    "source",
                    "username",
                    "password",
                    "recordings",
                )
            },
        ),
        (
            _("URLs"),
            {
                "classes": ("collapse",),
                "fields": ("url_authentication", "url_ready", "url_not_ready"),
            },
        ),
    )
    readonly_fields = ("url_authentication", "url_ready", "url_not_ready")

    def url_authentication(self, obj):
        path = reverse("video:push-auth", kwargs={"pk": obj.pk})
        return format_html("""<a href="{}"><code>{}</code></a>""", path, path)

    format_html.short_description = _("Authentication")

    def url_ready(self, obj):
        path = reverse("video:push-ready", kwargs={"pk": obj.pk})
        return format_html("""<a href="{}"><code>{}</code></a>""", path, path)

    url_ready.short_description = _("Ready")

    def url_not_ready(self, obj):
        path = reverse("video:push-not-ready", kwargs={"pk": obj.pk})
        return format_html("""<a href="{}"><code>{}</code></a>""", path, path)

    url_not_ready.short_description = _("Not ready")


@admin.register(models.PushProtocol)
class PushProtocolAdmin(admin.ModelAdmin):
    list_display = ("name", "identifier")


class LiveTemplateStreamInline(admin.TabularInline):
    model = models.LiveTemplateStream


@admin.register(models.LiveTemplateScene)
class LiveTemplateSceneAdmin(admin.ModelAdmin):
    list_filter = ("template",)
    search_fields = ("name",)
    inlines = (LiveTemplateStreamInline,)
    actions = ("public", "private")

    def public(self, request, queryset):
        for e in queryset.all():
            le = e.instantiate(True)
            if le.start():
                self.message_user(
                    request,
                    _("Live event {} was started.").format(le),
                    messages.SUCCESS,
                )
            else:
                le.stop()
                self.message_user(
                    request,
                    _("Live event {} failed to start.").format(le),
                    messages.ERROR,
                )

    public.short_description = _("Start new public live events")

    def private(self, request, queryset):
        for e in queryset.all():
            le = e.instantiate(False)
            if le.start():
                self.message_user(
                    request,
                    _("Live event {} was started.").format(le),
                    messages.SUCCESS,
                )
            else:
                le.stop()
                self.message_user(
                    request,
                    _("Live event {} failed to start.").format(le),
                    messages.ERROR,
                )

    private.short_description = _("Start new private live events")


class LiveEventChildAdmin(PolymorphicChildModelAdmin):
    base_model = models.LiveEvent
    search_fields = ("title", "description")
    date_hierarchy = "begin"
    readonly_fields = ("statistics_link",)

    def stop(self, request, queryset):
        for e in queryset.all():
            e.stop()

    stop.short_description = _("Stop selected live events")

    def get_urls(self):
        urls = super().get_urls()
        urls += [
            url(
                r"^statistics/(?P<pk>\w+)$",
                self.statistics_file,
                name="video_liveevent_statistics",
            ),
        ]
        return urls

    def statistics_link(self, obj):
        return format_html(
            '<a href="{}">XLSX</a>',
            reverse("admin:video_liveevent_statistics", args=[obj.pk]),
        )

    statistics_link.short_description = "Statistics"

    def statistics_file(self, request, pk):
        response = HttpResponse()
        le = models.LiveEvent.objects.get(pk=pk)
        mt = le.excel(response)
        response["Content-Type"] = mt
        response["Content-Disposition"] = f'attachment; filename="{le.pk}.xlsx"'
        return response


class LiveStreamInline(admin.TabularInline):
    model = models.LiveStream


class LiveViewerInline(admin.TabularInline):
    model = models.LiveViewer


class PushLiveIngestInline(admin.TabularInline):
    model = models.PushLiveIngest

    #fields = ()
    readonly_fields = ("url",)


@admin.register(models.LiveEvent)
class LiveEventAdmin(PolymorphicParentModelAdmin):
    list_display = ("pk", "title", "started", "begin", "end", "public")
    list_filter = ("public", "begin", "end")
    search_fields = ("title", "description")
    date_hierarchy = "begin"
    inlines = (LiveStreamInline, LiveViewerInline)
    actions = ("start", "stop")
    readonly_fields = ("statistics_link",)
    child_models = (models.OnDemandLiveEvent, models.PushLiveEvent)
    list_filter = (PolymorphicChildModelFilter,)

    def start(self, request, queryset):
        for e in queryset.all():
            e.start()

    start.short_description = _("Start selected live events")

    def stop(self, request, queryset):
        for e in queryset.all():
            e.stop()

    stop.short_description = _("Stop selected live events")

    def get_urls(self):
        urls = super().get_urls()
        urls += [
            url(
                r"^statistics/(?P<pk>\w+)$",
                self.statistics_file,
                name="video_liveevent_statistics",
            ),
        ]
        return urls

    def statistics_link(self, obj):
        return format_html(
            '<a href="{}">XLSX</a>',
            reverse("admin:video_liveevent_statistics", args=[obj.pk]),
        )

    statistics_link.short_description = "Statistics"

    def statistics_file(self, request, pk):
        response = HttpResponse()
        le = models.LiveEvent.objects.get(pk=pk)
        mt = le.excel(response)
        response["Content-Type"] = mt
        response["Content-Disposition"] = f'attachment; filename="{le.pk}.xlsx"'
        return response


@admin.register(models.OnDemandLiveEvent)
class OnDemandLiveEventAdmin(LiveEventChildAdmin):
    base_model = models.OnDemandLiveEvent
    show_in_index = True
    list_display = ("pk", "channel", "title", "started", "begin", "end", "public")
    list_filter = ("channel", "public", "begin", "end")
    inlines = (LiveStreamInline, LiveViewerInline)
    actions = ("start", "stop")

    def start(self, request, queryset):
        for e in queryset.all():
            e.start()

    start.short_description = _("Start selected live events")


@admin.register(models.PushLiveEvent)
class PushLiveEventAdmin(LiveEventChildAdmin):
    base_model = models.PushLiveEvent
    show_in_index = True
    list_display = ("pk", "title", "started", "begin", "end", "public")
    list_filter = ("public", "begin", "end")
    inlines = (PushLiveIngestInline, LiveStreamInline, LiveViewerInline)
    actions = ("stop",)

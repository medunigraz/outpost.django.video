from appconf import AppConf
from django.conf import settings


class VideoAppConf(AppConf):
    EPIPHAN_PROVISIONING = False
    CRATES_RECORDING_URL = "http://localhost/recording/online/{pk}"

    class Meta:
        prefix = "video"

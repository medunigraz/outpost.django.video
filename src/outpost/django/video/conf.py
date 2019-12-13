from appconf import AppConf
from django.conf import settings


class VideoAppConf(AppConf):
    EPIPHAN_PROVISIONING = False
    CRATES_RECORDING_URL = "http://localhost/recording/online/{pk}"
    RECORDING_UPLOAD_SERVER_ENCRYPTION = [
        "chacha20-poly1305@openssh.com",
        "aes256-ctr",
        "aes192-ctr",
        "aes128-ctr",
        "aes256-gcm@openssh.com",
        "aes128-gcm@openssh.com",
    ]
    RECORDING_UPLOAD_SERVER_MAC = [
        "hmac-sha2-256-etm@openssh.com",
        "hmac-sha2-512-etm@openssh.com",
        "hmac-sha2-256",
        "hmac-sha2-512",
    ]
    TRANSCRIBE_BUCKET = None

    class Meta:
        prefix = "video"

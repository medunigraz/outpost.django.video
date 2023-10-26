from datetime import timedelta

from appconf import AppConf
from django.conf import settings
from django.utils import timezone
import geoip2.database import Reader


class VideoAppConf(AppConf):
    EPIPHAN_PROVISIONING = False
    EPIPHAN_PREVIEW = False
    EPIPHAN_PREVIEW_TIMEOUT = 200000
    EPIPHAN_PREVIEW_ANALYZE_DURATION = 100000000
    CELERY_QUEUE = "video"
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
    AUPHONIC_URL = "https://auphonic.com/api/"
    AUPHONIC_USERNAME = None
    AUPHONIC_PASSWORD = None
    AUPHONIC_FORMAT = "flac"
    AUPHONIC_CHUNK_SIZE = 8192
    AUPHONIC_SILENCE_THRESHOLD = 0.9
    LIVE_HLS_SEGEMENT = 2
    LIVE_VIEWER_LIFETIME = timedelta(days=1)
    LIVE_DELIVERY_NOW_FORMAT = "%a, %d %b %Y %H:%M:%S %Z"
    LIVE_DELIVERY_NOW_TIMEZONE = timezone.pytz.timezone("Etc/GMT")
    LIVE_STARTUP_ATTEMPTS = 30
    LIVE_STARTUP_WAIT = 2
    GEOIP_DATABASE = Reader("/var/lib/GeoIP/GeoLite2-City.mmdb")

    class Meta:
        prefix = "video"

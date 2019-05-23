from . import api

v1 = [
    (r"video/exportclass", api.ExportClassViewSet, "video-exportclass"),
    (r"video/recorder", api.RecorderViewSet, "video-recorder"),
    (r"video/epiphan", api.EpiphanViewSet, "video-epiphan"),
    (r"video/epiphanchannel", api.EpiphanChannelViewSet, "video-epiphanchannel"),
    (r"video/epiphansource", api.EpiphanSourceViewSet, "video-epiphansource"),
    (r"video/recording", api.RecordingViewSet, "video-recording"),
    (r"video/recordingasset", api.RecordingAssetViewSet, "video-recordingasset"),
]

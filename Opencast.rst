====================
Opencast Integration
====================

This document outlines the integration between Opencast (Portal) and the
API server for managing live events.


A live event is started
=======================

When a live event is initiated on the API server, it issues a HTTPS request to
Opencast, containing a JSON body with all the information regarding this live
event.

A HTTP status code of *200* is treated as success, all other status codes are to be
treated as a failure to notify Opencast of this new live event.

.. code-block:: http
    :linenos:

    PUT /<path_to_opencast>/ HTTP/1.1
    Host: vital.medunigraz.at
    Content-Type: application/json

    {
        "id": "<channelid>",
        "viewer": "https://api.medunigraz.at/video/live/viewer/<eventid>/",
        "title": "lorem ipsum",
        "description": "Lorem <strong>ipsum dolor</strong> sit amet, <a href=\"https://www.medunigraz.at/\">consetetur</a> sadipscing elitr, ...",
        "unrestricted": true
        "previews": {
            "presenter": [
                "https://1.asd.medunigraz.at/livestream/<eventid>/<stream1id>.jpg",
                "https://2.asd.medunigraz.at/livestream/<eventid>/<stream1id>.jpg"
            ],
            "slides": [
                "https://1.asd.medunigraz.at/livestream/<eventid>/<stream1id>.jpg",
                "https://2.asd.medunigraz.at/livestream/<eventid>/<stream1id>.jpg"
            ]
        }
    }

Keys
----

`.id`: The unique channel ID in which this live event should be listed.
`.viewer`: The URL to use when creating new viewers.
reference this live event on the API server in various requests.
`.title`: Titel of the live event
`.description`: Teaser/Description of the live event, may contain HTML.
`.unrestricted`: Boolean flag that singals if the event is public (`true`) or private (`false`).
`.previews`: A dictionary of live streams used in this event (keys are usually *presenter* and *slides*).
`.previews.<stream>`: A list of URLs for preview images of the live stream. A user-facing portal should randomly select one URL from this list and present it to the user. The preview images will be updated at an interval of 10 seconds.

A live event is stopped
=======================

If the API server is requested to stop a live event, it will send a HTTPs request to Opencast to signal the end of the live event.

A HTTP status code of *200* is treated as success, all other status codes are to be
treated as a failure to notify Opencast of the end of the live event.

.. code-block:: http
    :linenos:

    DELETE /<path_to_opencast>/ HTTP/1.1
    Host: vital.medunigraz.at
    Content-Type: application/json

    {
        "id": "<channelid>"
    }

Keys
----
`.id`: The unique ID of the channel where a live event has ended.


Creating a new viewer
=====================

A viewer is a user who wants to consume the live event. To distinguish each
consumer on the delivery server for authentication and statistics, a unique ID
is generated for each viewer and it is encoded into the stream URLs.

This is handeld by sending a HTTPS request to the API server. The exact URL for
this request is included in the JSON payload when Opencast is notified of a new
live event, see `.viewer`.

A HTTP status code of *200* signals success, all other status codes are to be
treated as a failure to create a new viewer (e.g. because the live event has
already ended or does not exist).

The <IPv4/IPv6 of Client> needs to be set to the remote address of the client
machine that wants to consume the stream.

.. code-block:: http
    :linenos:

    PUT /video/live/viewer/<eventid>/
    Host: api.medunigraz.at
    Content-Type: application/json; charset=utf-8

    {"client": "<IPv4/IPv6 of Client>"}

If successful, this will respond with a JSON body containing information about
the newly created viewer.

.. code-block:: http
    :linenos:

    HTTP/1.1 200 OK
    Content-Type: application/json

    {
        "viewer": "<viewerid>",
        "streams": {
            "presenter": "https://2.asd.medunigraz.at/livestreams/<eventid>/<stream1id>/<viewerid>.m3u8",
            "slides": "https://2.asd.medunigraz.at/livestreams/<eventid>/<stream2id>/<viewerid>.m3u8"
        }
    }

Keys
----

`.viewer`: The unique ID assigned to this viewer.
`.streams`: Ein Dictionary aus verschiedenen Streams (meist wohl "presenter" und "slides")
`.streams`: A dictionary of live streams used in this event (keys are usually *presenter* and *slides*).
`.streams.<stream>`: The URL to the M3U8 playlist for this stream. The URL is only valid for a single viewer.

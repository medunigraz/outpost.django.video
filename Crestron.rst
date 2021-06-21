====================
Crestron Integration
====================

This document outlines the integration between Creston (Touchpanels) and the
API server for managing live events.


Starting a live event
=====================

If a user on the Crestron panel wants to initiate a live stream they have to
select a scene and Creston has to singal the user's choice to the API server.

This is done through HTTPS requests with all the relevant information encoded
into the URL.

A HTTP status code of *200* signals success, all other status codes are to be
treated as a failure to start the live event.

Public
----------

If the user has the selected to make this stream publicly available.

.. code-block:: http
    :linenos:

    POST /video/live/room/<templateid>/<sceneid>/public/ HTTP/1.1
    Host: api.medunigraz.at

Private
-------

If the user has the selected to make this stream private, i.e. only for
authenticated users.

.. code-block:: http
    :linenos:

    POST /video/live/room/<templateid>/<sceneid>/ HTTP/1.1
    Host: api.medunigraz.at


Stopping a live event
=====================

A running live stream can be stopped by the user through the Creston panel. In
this case Creston has to signal the end of the live stream to the API server by
issuing another HTTPS request.

A HTTP status code of *200* signals success, all other status codes are to be
treated as a failure to stop the live event.

.. code-block:: http
    :linenos:

    DELETE /video/live/room/<templateid>/ HTTP/1.1
    Host: api.medunigraz.at



Quering the status of a room
============================

In order to maintain consitency between the API server an Creston, it is
requried to periodically query the status of a room gerading any running live
streams. The interval between status queries can be as small as 2 seconds.

A HTTP status code of *200* signals an active and running live event for this
room while *404* signals no active live event. All other status codes are to be
treated as a failure to query the status of the room.

.. code-block:: http
    :linenos:

    GET /video/live/room/<templateid>/ HTTP/1.1
    Host: api.medunigraz.at

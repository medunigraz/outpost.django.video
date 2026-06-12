Transcoder Server Setup
=======================

NVIDIA
------



FFMPEG
------

NGINX
-----

Make sure nginx has a runtime directory available where sockets can be placed.

.. ::

  echo "[Service]\nRuntimeDirectory=nginx" |sudo tee -a /etc/systemd/system/nginx.service.d/override.conf
  sudo systemctl daemon-reload

Create a virtual host configuration at ``/etc/nginx/sites-available/transcoder.example.org``.

.. ::

  map $http_accept $webp_suffix {
          default    "";
          "~*image/webp" ".webp";
  }

  server {
          listen unix:/run/nginx/transcoder.example.com.sock;
          server_name transcoder.example.com;

          root /var/www/vhosts/transcoder.example.com;

          location ~* \.(png|jpg|jpeg)$ {
                  try_files $uri$webp_suffix $uri =404;
                  add_header Vary Accept;
                  add_header Cache-Control "public, no-transform, immutable";
                  aio threads;
          }

          location / {
                  try_files $uri =404;
                  aio threads;
          }

  }

Create a symlink to enable the site and restart ``nginx.service``.

.. ::

  sudo ln -s ../sites-available/transcoder.example.org /etc/nginx/sites-enabled/transcoder.example.org
  sudo systemctl restart nginx.service

Backend
-------

Prepare the SSH tunnel for UNIX domain socket forwarding.

.. ::

  sudo mkdir ~www-data/.ssh

Prepare the SSH configuration in ``~www-data/.ssh/config``, be sure to replace ``[N]`` with the number of the transcoding server.

.. ::

  Match tagged backend
      User varnish
      IdentityFile ~/.ssh/backend
      IdentitiesOnly yes
      RemoteForward /run/backend/transcoder.example.com.sock /run/nginx/transcoder.example.com.sock

Place the private SSH key at ``~www-data/.ssh/backend``. Then set the correct permissions.

.. ::

  sudo chmod -R go-rx ~www-data/.ssh
  sudo chown -R www-data ~www-data/.ssh

Test the SSH connection for each delivery server and accept their hosts keys if the are correct.

.. ::

  sudo -u www-data ssh -N -P backend delivery.example.com

Create a systemd service template at ``/etc/systemd/system/backend@.service``.

.. ::

  [Unit]
  Description=Backend Tunnel %i

  Wants=network-online.target nginx.service
  After=network.target network-online.target nginx.service

  [Service]
  Type=simple
  User=www-data
  ExecStart=/usr/bin/ssh -N -P backend %i
  KillMode=process
  Restart=always
  RestartSec=5
  SyslogIdentifier=backend@%i

  [Install]
  WantedBy=multi-user.target

Start a service instance for each delivery server.

.. ::

   sudo systemctl enable --now backend@delivery.example.com.service

If the delivery server was correctly configured, it should have a socket usable at ``/run/backend/transcoder.example.com.sock``. Test it with ``curl`` on the
delivery server.

.. ::

   curl --silent --show-error --unix-socket /run/backend/transcoder.example.com.sock http://transcoder.example.com/

Varnish
-------



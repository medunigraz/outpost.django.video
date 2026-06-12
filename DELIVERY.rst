Transcoder Server Setup
=======================

Backend
-------

Make sure that local sockets can be unlinked:

.. ::

  echo "StreamLocalBindUnlink yes" | sudo tee -a /etc/ssh/sshd_config.d/mug.conf
  sudo systemctl restart ssh.service

Assign a home directory to the varnish user:

.. ::

   sudo usermod -d /var/lib/varnish varnish

Prepare for incoming SSH connections:

.. ::

   sudo mkdir ~varnish/.ssh
   echo 'no-pty,command="/usr/sbin/nologin" ssh-ed25519 [PUBLIC KEY] transcoder' |sudo tee -a
   ~varnish/.ssh/authorized_keys
   sudo chmod -R go-wx ~varnish/.ssh
   sudo chown -R varnish ~varnish/.ssh

Make sure that the runtime directory for the incoming sockets is created at boot time:

.. ::

   echo 'd     /run/backend   0755 varnish root   -   -' |sudo tee -a /etc/tmpfiles.d/backend.conf
   sudo systemd-tmpfiles --create

Varnish
-------

Hitch
-----

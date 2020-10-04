#!/bin/bash
#
# Ugly workaround that modifies uids and gids for specified users
# in order to sync them with the host.
# Won't credit myself about this.
#

# Look at /var/lib/aptly-api/db for clues on how
# to change permissions
API_USER=$(stat -c '%u' /var/lib/aptly-api/db)
API_GROUP=$(stat -c '%g' /var/lib/aptly-api/db)

# Do the same for the queue, looking at
# /srv/aptly-queue
QUEUE_USER=$(stat -c '%u' /srv/aptly-queue)
QUEUE_GROUP=$(stat -c '%g' /srv/aptly-queue)

# Now do the dance
usermod -u ${API_USER} aptly-api
groupmod -g ${API_GROUP} aptly-api

usermod -u ${QUEUE_USER} aptly-queue
groupmod -g ${QUEUE_GROUP} aptly-queue

# Fix permission of the configuration file
chown root:aptly-api /etc/aptly-api.conf

# Re-run systemd-tmpfiles so that uids are synced
systemd-tmpfiles --create --exclude-prefix=/dev

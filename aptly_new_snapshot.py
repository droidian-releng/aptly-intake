#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# aptly-intake - pick up and publish with aptly
# Copyright (C) 2020 Eugenio "g7" Paolantonio <me@medesimo.eu>
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above copyright
#      notice, this list of conditions and the following disclaimer in the
#      documentation and/or other materials provided with the distribution.
#    * Neither the name of the <organization> nor the
#      names of its contributors may be used to endorse or promote products
#      derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import os

import sys

import uuid

import configparser

import aptly_api

from debian.deb822 import Changes

ALLOWED_DISTRIBUTIONS = [
	"bullseye",
	"bookworm",
]

# How does the publishing work:
#  1. This script is invoked by a watcher whenever a new .changes
#     file appears
#  2. Every file referenced in the .changes file gets uploaded to
#     a new directory in aptly
#  3. A lock is acquired
#  4. The files are included in the local repo
#  5. Every component is snapshotted
#  6. The new snapshots gets published
#  7. Lock is released

INTAKE_SETTINGS = "/var/lib/aptly-api/intake-settings"

config = configparser.ConfigParser()
config.read(INTAKE_SETTINGS)

DEFAULT_VENDOR = config.get(
	"Intake",
	"APTLY_DEFAULT_VENDOR",
	fallback="Droidian"
)
DEFAULT_SIGNING_GPG_FINGERPRINT = config.get(
	"Intake",
	"APTLY_SIGNING_GPG_FINGERPRINT",
	fallback="3027CDD5DF3C0181264550A062F62D66F658C408"
)
DEFAULT_SIGNING_GPG_KEYRING = config.get(
	"Intake",
	"APTLY_SIGNING_GPG_KEYRING",
	fallback="/var/lib/aptly-api/.gnupg/pubring.kbx"
)

# FIXME?
DEFAULT_ARCHITECTURES = [
	"source",
	"amd64",
	"i386",
	"arm64",
	"armhf",
]

if __name__ == "__main__":
	run_uuid = uuid.uuid4()

	signing_configuration = aptly_api.AptlyAPISigningOptions(
		[
			("Skip", False),
			("GpgKey", DEFAULT_SIGNING_GPG_FINGERPRINT),
		]
	)

	with aptly_api.AptlySession("http://localhost:8080/") as session:

		with aptly_api.AptlyAPILock() as lock:
			# Get the list of local repositories related to the current
			# channel and distribution combo
			repo_list = session.LocalRepo.list()

			channels_and_distributions = {
				"_".join(x["Name"].split("_")[:2])
				for x in repo_list if "_" in x["Name"] # meh
			}

			for channel_and_distribution in channels_and_distributions:
				channel, distribution = channel_and_distribution.split("_")

				repos = {
					x["Name"] : x["DefaultComponent"] # FIXME: this is an assumption we make
					for x in repo_list
					if x["Name"].startswith("%s_%s_" % (channel, distribution))
				}

				created_snapshots = []
				for repo, component in repos.items():
					snapshot_name = "%s_%s" % (repo, run_uuid)
					print("Creating snapshot for repo %s" % repo)
					session.LocalRepo(name=repo).snapshot(snapshot_name)
					created_snapshots.append(
						{
							"Component" : component,
							"Name" : snapshot_name
						}
					)

				# Switch
				target_published_distribution = session.PublishedDistribution(
					prefix=channel,
					distribution=distribution,
				)

				target_published_distribution.update(
					snapshots=created_snapshots,
					signing=signing_configuration,
					force_overwrite=True,
				)

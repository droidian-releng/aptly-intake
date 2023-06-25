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
	"trixie",
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
	# Open changes files as specified in the command line
	if len(sys.argv) == 2:
		changes_path = os.path.abspath(sys.argv[1])
		with open(changes_path, "r") as f:
			changes = Changes(f)
	else:
		raise Exception("No (or too many) .changes files has been specified")

	run_uuid = uuid.uuid4()

	with aptly_api.AptlySession("http://localhost:8080/") as session:

		base_directory = os.path.dirname(changes_path)

		# Obtain distribution
		distribution = changes["Distribution"]

		# We assume the channel is the directory name
		channel = os.path.basename(base_directory)

		if not distribution in ALLOWED_DISTRIBUTIONS:
			raise Exception("Distribution %s not allowed" % distribution)

		touched_components = set()
		for referenced_file in changes["files"]:
			component = referenced_file["section"].split("/")[0] \
				if "section" in referenced_file and "/" in referenced_file["section"] \
				else "main"

			# Create a new directory and upload every referenced file
			upload_directory = session.Directory(dir="%s-%s" % (run_uuid, component))

			full_filepath = os.path.join(base_directory, referenced_file["name"])

			with open(full_filepath, "r+b") as f:
				print("Uploading %s" % full_filepath)
				upload_directory.upload(f)

				# Truncate rather than removing as we might not be
				# able to write to the upload directory
				f.truncate(0)

			touched_components.add(component)

		# Upload the changes file for every component
		# FIXME: Is this wrong?
		for component in touched_components:
			upload_directory = session.Directory(dir="%s-%s" % (run_uuid, component))

			with open(changes_path, "rb") as f:
				print("Uploading changes file %s on touched component %s" % (changes_path, component))
				upload_directory.upload(f)

		# Now we should operate on the aptly database directly, so
		# obtain a lock...
		with aptly_api.AptlyAPILock() as lock:
			# Get the list of local repositories related to the current
			# channel and distribution combo
			repos = {
				x["Name"] : x["DefaultComponent"] # FIXME: this is an assumption we make
				for x in session.LocalRepo.list()
				if x["Name"].startswith("%s_%s_" % (channel, distribution))
			}

			# We should create a new repository?
			for component in touched_components:

				# Construct target repository name, which boils down to
				#  channel_distribution_component
				target_repository_name = "%s_%s_%s" % (
					channel,
					distribution,
					component
				)

				if not target_repository_name in repos:
					# Create a new repository
					session.LocalRepo.create(
						target_repository_name,
						comment="Local repository for %s/%s" % (
							distribution,
							component
						),
						default_distribution=distribution,
						default_component=component
					)
					repos[target_repository_name] = component

				# Now include the new packages
				print("Importing packages for component %s" % component)
				res = session.RepositoryDirectory(
					name=target_repository_name,
					dir="%s-%s" % (run_uuid, component)
				).include()
				print("Result of import is %s" % res)

			# Local repo is ok now, snapshot every repository and
			# re-publish them
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

			# Obtain the list of published repositories
			channel_published = (channel, distribution) in [
				(x["Prefix"], x["Distribution"])
				for x in session.PublishedRepo.list()
			]

			signing_configuration = aptly_api.AptlyAPISigningOptions(
				[
					("Skip", False),
					("GpgKey", DEFAULT_SIGNING_GPG_FINGERPRINT),
				]
			)

			for publish_try in range(0, 2):
				# We should try two times due to how aptly behaves when
				# switching snapshots on an already published repository
				# when a new component has been added.

				if channel_published:
					# Switch
					target_published_distribution = session.PublishedDistribution(
						prefix=channel,
						distribution=distribution,
					)

					try:
						target_published_distribution.update(
							snapshots=created_snapshots,
							signing=signing_configuration,
							force_overwrite=True,
						)
					except Exception as e:
						if "not in published repository" in str(e):
							# Trying to publish an unpublished component,
							# drop the published repo and try again from
							# scratch
							target_published_distribution.delete()
							channel_published = False
							continue
				else:
					# Create new published repository
					session.PublishedRepo(prefix=channel).publish(
						"snapshot",
						created_snapshots,
						distribution=distribution,
						label="%s (%s channel)" % (DEFAULT_VENDOR, channel),
						origin=DEFAULT_VENDOR,
						architectures=DEFAULT_ARCHITECTURES,
						signing=signing_configuration,
						force_overwrite=True,
					)

				break

	# Remove changes files
	with open(changes_path, "w") as f:
		f.truncate(0)

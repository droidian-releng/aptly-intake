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

import apt_pkg

import aptly_api

from functools import reduce

def get_packages_to_remove(packages_per_arch, keep=3):
	"""
	Returns a list of packages to remove.

	:param: packages_per_arch: a dictionary containing the packages to filter
	:param: keep: the number of versions of the same package to keep (defaults
	to 3)
	"""

	to_remove = []

	for arch, packages in packages_per_arch.items():
		for package, versions in packages.items():
			to_keep = []

			if len(versions) <= keep:
				# Go to the next package
				continue

			_versions = list(versions.keys())
			for i in range(0, keep):
				winner = reduce(
					lambda x, y : x if apt_pkg.version_compare(x, y) > 0 else y,
					_versions
				)

				_versions.remove(winner)
				to_keep.append(winner)

			to_remove += [ref for version, ref in versions.items() if version not in to_keep]

	return to_remove

if __name__ == "__main__":
	apt_pkg.init_system()

	with aptly_api.AptlySession("http://localhost:8080") as session:
		with aptly_api.AptlyAPILock() as lock:
			# Remove old packages
			for repository in session.LocalRepo.list():
				repo = session.LocalRepo(name=repository["Name"])
				packages_per_arch = {}

				for ref in repo.search():
					arch, name, version, _ = ref.split(" ")
					packages_per_arch.setdefault(arch, {}).setdefault(name, {})[version] = ref

				to_remove = get_packages_to_remove(packages_per_arch)

				print("Repo: %s, removing: %s" % (repository["Name"], "\n    - ".join(to_remove)))

				repo.delete_packages(to_remove)

			# Remove old snapshots
			for snapshot in session.Snapshot.list():
				snap = session.Snapshot(name=snapshot["Name"])
				# Always try deleting, aptly will complain if it's published
				try:
					snap.delete()
				except Exception as e:
					if "snapshot is published" in str(e):
						# Safely continue
						continue
					else:
						# Shouldn't reach this
						raise
				else:
					print("Removed snapshot %s" % snapshot["Name"])

			# Cleanup
			subprocess.check_call(["aptly", "db", "cleanup", "-config", "/etc/aptly-api.conf", "-dep-follow-all-variants", "-dep-follow-source"])

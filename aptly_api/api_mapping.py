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

import requests

from typing import List

from collections import namedtuple

globals().update(
	{
		x : getattr(requests.Session, x)
		for x in ["get", "post", "put", "delete"]
	}
)

def snake_to_camel(string):
	"""
	Converts the supplied string from snake_case to CamelCase, and
	returns that.

	:param: string: the string to convert
	"""

	return "".join(
		(
			x.capitalize()
			for x in string.lower().split("_")
		)
	)

def convert_param(obj, param_type):
	"""
	Checks and converts the object given against the param_type,
	and converts it if it should be done.

	Returns the converted params, or raises an exception.

	:param: obj: the object to check and eventually convert
	:param: param_type: the type to check against
	"""

	real_type = type(obj)

	if param_type == int and real_type == bool:
		return int(obj)
	elif real_type == param_type:
		return obj
	else:
		raise Exception(
			"Expected object of type %s, got %s" % (
				param_type,
				real_type
			)
		)

class APIDescription(namedtuple("_APIDescription", [
	"method",
	"route",
	"route_format_expansion",
	"required_params",
	"optional_params",
	"query_params",
	"post_file",
])):
	def __new__(cls, *args, **kwargs):

		new_kwargs = {
			"method" : get,
			"route_format_expansion" : {},
			"required_params" : {},
			"optional_params" : {},
			"query_params" : {},
			"post_file" : False,
		}
		new_kwargs.update(kwargs)

		return super().__new__(cls, *args, **new_kwargs)

class KeyBlockedValueTypeCheckedDictionary(dict):

	"""
	A dictionary which blocks the keys to the one specified into the
	allowed_keys dictionary, and checks the type of the incoming values.
	"""

	allowed_keys = {}

	def __setitem__(self, key, value):
		"""
		Sets the item if both key and value are strings and the key
		is into allowed_keys.
		"""

		if not key in allowed_keys:
			raise Exception("Key %s not in allowed_keys" % key)

		if not isinstance(value, allowed_keys[key]):
			raise Exception("Value is not an instance of str")

		super().__setitem__(key, value)

class AptlyAPISigningOptions(KeyBlockedValueTypeCheckedDictionary):

	"""
	Aptly API Signing Options
	"""

	allowed_keys = {
		"Skip" : bool,
		"Batch" : bool,
		"GpgKey" : str,
		"Keyring" : str,
		"SecretKeyring" : str,
		"Passphrase" : str,
		"PassphraseFile" : str,
	}

class AptlyAPISnapshots(KeyBlockedValueTypeCheckedDictionary):

	"""
	Aptly API Snapshots
	"""

	allowed_keys = {
		"Component" : str,
		"Name" : str,
	}

aptly_mapping = {
	"LocalRepo" : {
		"@list" : APIDescription(
			method=get,
			route="/api/repos",
		),
		"@create" : APIDescription(
			method=post,
			route="/api/repos",
			required_params={
				"Name" : str,
			},
			optional_params={
				"Comment" : str,
				"DefaultDistribution" : str,
				"DefaultComponent" : str
			}
		),
		"show" : APIDescription(
			method=get,
			route="/api/repos/%(name)s",
		),
		"search" : APIDescription(
			method=get,
			route="/api/repos/%(name)s/packages",
			query_params={
				"q" : str,
				"withDeps" : bool,
				"format" : str,
			}
		),
		"edit" : APIDescription(
			method=put,
			route="/api/repos/%(name)s",
			optional_params={
				"Comment" : str,
				"DefaultDistribution" : str,
				"DefaultComponent" : str,
			}
		),
		"delete" : APIDescription(
			method=delete,
			route="/api/repos/%(name)s",
			query_params={
				"force" : bool,
			}
		),
		"add_packages" : APIDescription(
			method=post,
			route="/api/repos/%(name)s/packages",
			required_params={
				"PackageRefs" : list, # unsafe
			}
		),
		"delete_packages" : APIDescription(
			method=delete,
			route="/api/repos/%(name)s/packages",
			required_params={
				"PackageRefs" : list, # unsafe
			}
		),
		### Create snapshot from local repo
		"snapshot" : APIDescription(
			method=post,
			route="/api/repos/%(name)s/snapshots",
			required_params={
				"Name" : str,
			},
			optional_params={
				"Description" : str,
			},
		),
	},
	"RepositoryDirectory" : {
		"add" : APIDescription(
			method=post,
			route="/api/repos/%(name)s/file/%(dir)s",
			query_params={
				"noRemove" : bool,
				"forceReplace": bool,
			}
		),
		"include" : APIDescription(
			method=post,
			route="/api/repos/%(name)s/include/%(dir)s",
			query_params={
				"noRemoveFiles" : bool,
				"forceReplace" : bool,
				"ignoreSignature" : bool,
				"acceptUnsigned" : bool,
			}
		),
	},
	"Directory" : {
		"@list_directories" : APIDescription(
			method=get,
			route="/api/files",
		),
		"upload" : APIDescription(
			method=post,
			route="/api/files/%(dir)s",
			post_file=True
		),
		"list" : APIDescription(
			method=get,
			route="/api/files/%(dir)s",
		),
		"delete" : APIDescription(
			method=delete,
			route="/api/files/%(dir)s",
		),
	},
	"File" : {
		"delete" : APIDescription(
			method=delete,
			route="/api/files/%(dir)s/%(file)s",
		),
	},
	"Snapshot" : {
		### List
		"@list" : APIDescription(
			method=get,
			route="/api/snapshots",
		),
		### Create snapshot from package refs
		"@create" : APIDescription(
			method=post,
			route="/api/snapshots",
			required_params={
				"Name" : str
			},
			optional_params={
				"Description" : str,
				"SourceSnapshots" : list,
				"PackageRefs" : list,
			},
		),
		### Update
		"update" : APIDescription(
			method=put,
			route="/api/snapshots/%(name)s",
			optional_params={
				"Name" : str,
				"Description" : str,
			},
		),
		### Show
		"show" : APIDescription(
			method=get,
			route="/api/snapshots/%(name)s",
		),
		### Delete
		"delete" : APIDescription(
			method=delete,
			route="/api/snapshots/%(name)s",
		),
		### Show Packages/Search
		"search" : APIDescription(
			method=get,
			route="/api/snapshots/%(name)s/packages",
			query_params={
				"q" : str,
				"withDeps" : int,
				"format" : str,
			},
		),
	},
	"SnapshotDiff" : {
		### Difference between Snapshots
		"diff" : APIDescription(
			method=get,
			route="/api/snapshots/%(name)s/diff/%(with_snapshot)s",
		),
	},
	"PublishedRepo" : {
		### List
		"@list" : APIDescription(
			method=get,
			route="/api/publish",
		),
		### Publish snapshot/local repo
		"publish" : APIDescription(
			method=post,
			route="/api/publish/%(prefix)s",
			required_params={
				"SourceKind" : str,
				"Sources" : list, #List[str],
			},
			optional_params={
				"Distribution" : str,
				"Label" : str,
				"Origin" : str,
				"ForceOverwrite" : bool,
				"Architectures" : list, #List[str],
				"Signing" : AptlyAPISigningOptions,
				"NotAutomatic" : str,
				"ButAutomaticUpgrades" : str,
				"SkipCleanup" : bool,
				"AcquireByHash" : bool,
			},
		)
	},
	"PublishedDistribution" : {
		### Update published local repo/switch published snapshot
		"update" : APIDescription(
			method=put,
			route="/api/publish/%(prefix)s/%(distribution)s",
			optional_params={
				"Snapshots" : list, #List[AptlyAPISnapshots],
				"ForceOverwrite" : bool,
				"Signing" : AptlyAPISigningOptions,
				"AcquireByHash" : bool,
			},
		),
		### Drop published repository
		"delete" : APIDescription(
			method=delete,
			route="/api/publish/%(prefix)s/%(distribution)s",
			query_params={
				"force" : int,
			},
		),
	},
	# TODO: Packages
	# TODO: Misc
}

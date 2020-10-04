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

"""
Lightweight interface for aptly's REST API
"""

import os

import time

import requests

import urllib.parse

from contextlib import contextmanager

from .api_mapping import AptlyAPISigningOptions, snake_to_camel, convert_param, aptly_mapping

LOCK_FILE = "/run/aptly-intake/aptly-api-lock"

@contextmanager
def AptlyAPILock():
	if os.path.exists(LOCK_FILE):
		# Wait
		print("Lock file %s exists, waiting..." % LOCK_FILE)
		time.sleep(5)

	try:
		with open(LOCK_FILE, "w") as f:
			f.write("# File locked by aptly-intake\n")

		yield
	finally:
		os.remove(LOCK_FILE)

class AptlyAPIProxyObject:
	"""
	A proxy object for mapping sections.
	"""

	def __init__(self, session, section, parent=True, shared_state={}):
		"""
		Initialises the class.

		:param: session: an AptlySession() instance
		:param: section: the specified attribute
		:param: parent: if True (the default), allows the creation of
		child proxy objects via the `__call__` method. "Parent" objects
		will only allow static methods to be executed (the ones starting
		with `@` in the mapping)
		:param: shared_state: shared_state to be stored in the instance,
		this will be passed on the session's `_do_request()` method.
		"""

		self.session = session
		self.section = section
		self.parent = parent
		self.shared_state = shared_state

	def __getattr__(self, method):
		"""
		Returns a lambda function built from the given method.

		If self.parent is True, only "static" methods are allowed.
		"""

		if self.parent:
			method = "@%s" % method

		return lambda *args, **kwargs: \
			self.session._do_request(
				self.section,
				method,
				self.shared_state,
				*args,
				**kwargs
			)

	def __call__(self, **kwargs):
		"""
		Allows the returned proxy to be called and returns another proxy
		object with the same features as this one, but with parent set
		to False and kwargs set as the shared_state.

		Works only when self.parent == True
		"""

		if not self.parent:
			raise Exception("You can't use __call__() on a child proxy object!")

		return self.__class__(
			self.session,
			self.section,
			parent=False,
			shared_state=kwargs
		)

class AptlySession(requests.Session):
	"""
	An active session to aptly's API.

	The requests are lazily-made by looking at aptly_mapping (see
	`aptly_mapping.py`).
	"""

	def __init__(self, url):
		"""
		Initialises the class.

		:param: url: the url to connect to
		"""

		# TODO: Handle basic auth

		self.url = url

		super().__init__()

	def request(self, method, url, *args, **kwargs):
		"""
		Override to requests.Session().request() that automatically
		prefixes the base url when doing requests.
		"""

		return super().request(
			method=method,
			url=urllib.parse.urljoin(self.url, url),
			*args,
			**kwargs
		)

	def _do_request(self, section, method, shared_state, *args, **kwargs):
		"""
		Actually does the request following the description of
		the supplied method.
		"""

		# NOTE: We are basing ourselves on the fact that dictionaries
		# are ordered-by-default, which is an implementation detail
		# in CPython 3.6 and PyPy and spec since Python 3.7.

		description = aptly_mapping[section][method]

		# Check required arguments (args)

		# If we should upload a file (description.post_file), we assume
		# the first one is always the fileobject
		if description.post_file and len(args) > 0:
			_file_description = { "file" : args[0] }
			args = args[1:]
		else:
			_file_description = None

		if len(args) != len(description.required_params):
			raise Exception(
				"Expected %d arguments, got %d" % (
					len(args),
					len(description["required_params"])
				)
			)

		# Rebuild kwargs converting it to CamelCase
		final_kwargs = {
			**{
				snake_to_camel(x) : y
				for x, y in kwargs.items()
			},
			**{
				x : y
				for x, y in zip(description.required_params.keys(), args)
			},
		}

		# Build final arguments to pass to the request
		merged_params_description = {
			**description.required_params,
			**description.optional_params
		}
		body_params = {
			x : convert_param(y, merged_params_description[x]) 
			for x,y in final_kwargs.items()
			if not y is None
		}
		query_params = {
			x : convert_param(y, description.query_params[x])
			for x,y in final_kwargs.items()
			if not y is None and x in description.query_params
		}

		result = description.method(
			self,
			description.route % shared_state,
			files=_file_description,
			json=body_params,
			params=query_params,
		)

		if not (200 <= result.status_code < 300):
			try:
				error = result.json().get("error", "unknown error")
			except:
				error = "returned result is not JSON data"

			raise Exception(
				"Aptly API returned the following HTTP status code: %d. Error: %s" % (
					result.status_code,
					error
				)
			)

		return result.json()

	def __getattr__(self, attr):
		"""
		Returns an AptlyAPIProxyObject for the requested attribute.
		"""

		if not attr in aptly_mapping:
			raise Exception("%s not found in the API mapping" % attr)

		return AptlyAPIProxyObject(self, attr)

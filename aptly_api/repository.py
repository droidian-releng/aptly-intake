# -*- coding: utf-8 -*-
#
# aptly-intake - pick up and publish with aptly
# Copyright (C) 2020-2021 Eugenio "g7" Paolantonio <me@medesimo.eu>
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

from debian.deb822 import Release

import os

import gpg

import hashlib

import gzip

import email.utils

CHUNK_SIZE = 1024

class ExtraRelease(Release):
	"""
	A deb822 Release, with extra files.
	"""
	
	def __init__(self, *args, extra_files=[], **kwargs):
		"""
		Initializes the class.
		
		Important note! The files specified in the extra_files list
		must be relative to the Release file location.
		"""
		
		super().__init__(*args, **kwargs)

		self.extra_files = extra_files
		
	def parse_extras(self):
		"""
		Parses the extra files
		"""
		
		# Build the final list of files to digest - compressed files
		# must be uncompressed and parsed as well.
		# We assume that files with the same name (sans the compressed
		# file extension) are the same.
		files = set()
		
		for x in self.extra_files:
			target_file = x.replace("./", "")
			files.add(target_file)
			
			if target_file.endswith((".gz", ".bz2", ".xz")):
				files.add(".".join(target_file.split(".")[:-1]))
		
		# Finally do our things
		for file_ in files:
			hashes = {
				"MD5Sum" : hashlib.md5(),
				"SHA1" : hashlib.sha1(),
				"SHA256" : hashlib.sha256(),
				"SHA512" : hashlib.sha512(),
			}
			size = 0
			
			# If file doesn't exist, we assume that there is a gzipped-compressed
			# file with the .gz extension. We'll open that instead.
			# TODO: do the same with xz?
			if not os.path.exists(file_) and os.path.exists("%s.gz" % file_):
				with_gzip = True
				file_real = "%s.gz" % file_
			else:
				with_gzip = False
				file_real = file_

			with open(file_real, "rb") as f:
				if with_gzip:
					f = gzip.GzipFile(fileobj=f)

				while True:
					chunk = f.read(CHUNK_SIZE)

					if chunk != b"":
						for digestinstance in hashes.values():
							digestinstance.update(chunk)
					else:
						# Finished
						size = f.tell()
						break
				
				if with_gzip:
					f.close()
			
			# Update Release content
			for section, digestinstance in hashes.items():
				self[section].append(
					{
						section.lower() : digestinstance.hexdigest(),
						"size" : size,
						"name" : file_
					}
				)
				
		# Bump date
		self["Date"] = email.utils.formatdate(usegmt=True).replace("GMT", "UTC") # ????
		
	def dump_signature(self, fd, signers):
		"""
		Dumps the signature for the given file on the supplied fd.
		"""
		
		# TODO: do something when signing fails
		
		content = self.dump().encode("utf-8")
		
		with gpg.Context(armor=True, signers=signers) as ctx:
			result = ctx.sign(content, mode=gpg.constants.SIG_MODE_DETACH)
			
			fd.write(result[0])
	
	def dump_signature_cleartext(self, fd, signers):
		"""
		Dumps the signature in cleartext alongside the file contents.
		"""
		
		# TODO: do something when signing fails
		
		content = self.dump().encode("utf-8")
		
		with gpg.Context(armor=True, signers=signers) as ctx:
			result = ctx.sign(content, mode=gpg.constants.SIG_MODE_CLEAR)
			
			fd.write(result[0])

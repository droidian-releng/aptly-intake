#!/bin/bash
#

CONFIGURATION_FILE="/var/lib/aptly-api/intake-settings"
APPSTREAM_DB_BASE="/var/lib/aptly-api/appstream-db"
APPSTREAM_EXPORT_BASE="/var/lib/aptly-api/appstream-export"

ALLOWED_REPOSITORIES="production staging"
ALLOWED_SUITES="bullseye"

# FIXME?
ALLOWED_SECTIONS='["main"]'
ALLOWED_ARCHITECTURES='["amd64", "armhf", "arm64"]'

# Should we enable appstream?
if grep -q "^APPSTREAM_ENABLED=" ${CONFIGURATION_FILE}; then
	APPSTREAM_ENABLED="$(grep -oP 'APPSTREAM_ENABLED=\"?(yes|no)\"?' ${CONFIGURATION_FILE} | head -n 1 | cut -d '=' -f2 | sed 's/"//g')"
else
	APPSTREAM_ENABLED="no"
fi
[ "${APPSTREAM_ENABLED}" == "yes" ] || exit 0

# Try to get repository name
if grep -q "^VENDOR_NAME=" ${CONFIGURATION_FILE}; then
	VENDOR_NAME="$(grep -oP 'VENDOR_NAME=\"?[a-zA-Z0-9\\-\\_\\.\\ ]+\"?' ${CONFIGURATION_FILE} | head -n 1 | cut -d '=' -f2 | sed 's/"//g')"
else
	VENDOR_NAME="Droidian"
fi

# Try to get appstream metadata url
if grep -q "^APPSTREAM_METADATA_URL=" ${CONFIGURATION_FILE}; then
	APPSTREAM_METADATA_URL="$(grep -oP 'APPSTREAM_METADATA_URL=\"?[a-zA-Z0-9\\-\\_\\.\\ ]+\"?' ${CONFIGURATION_FILE} | head -n 1 | cut -d '=' -f2 | sed 's/"//g')"
else
	APPSTREAM_METADATA_URL="http://metadata-%repository.repo.droidian.org"
fi

for repository in ${ALLOWED_REPOSITORIES}; do
	# Create temporary directory
	tmpdir=$(mktemp -d)

	cleanup() {
		rm -rf ${tmpdir} || true
	}
	trap cleanup EXIT
	
	metadata_url=${APPSTREAM_METADATA_URL//%repository/${repository}}
	appstream_db_path="${APPSTREAM_DB_BASE}-${repository}"
	appstream_export_path="${APPSTREAM_EXPORT_BASE}-${repository}"
	
	if [ ! -e "${appstream_db_path}" ]; then
		mkdir ${appstream_db_path}
	fi
	ln -s ${appstream_db_path} ${tmpdir}/db

	if [ ! -e "${appstream_export_path}" ]; then
		mkdir ${appstream_export_path}
	fi
	ln -s ${appstream_export_path} ${tmpdir}/export

	# Create configuration file
	cat > ${tmpdir}/asgen-config.json <<EOF
{
"ProjectName": "${VENDOR_NAME}",
"ArchiveRoot": "/var/lib/aptly-api/public/${repository}",
"MediaBaseUrl": "${metadata_url}/appstream/media",
"Backend": "debian",
"Icons" : {
	"64x64": {"cached": true, "remote": false},
	"128x128": {"cached": false, "remote": true}
},
"Suites" : {
EOF

	for suite in ${ALLOWED_SUITES}; do
		cat >> ${tmpdir}/asgen-config.json <<EOF
	"${suite}": { "sections": ${ALLOWED_SECTIONS}, "architectures": ${ALLOWED_ARCHITECTURES} },
EOF
	done
	
	cat >> ${tmpdir}/asgen-config.json <<EOF
	"bogus-suite": { "sections": [], "architectures": [] }
}
}
EOF

	# Run appstream generator
	cd ${tmpdir}
	for suite in ${ALLOWED_SUITES}; do
		appstream-generator process ${suite}
		
		if [ -e ${appstream_export_path}/data/${suite} ]; then
			for section in ${appstream_export_path}/data/${suite}/*; do
				_target="/var/lib/aptly-api/public/${repository}/dists/${suite}/$(basename ${section})/dep11"
				rm -rf ${_target}
				cp -Rv ${section} ${_target}
			done
		fi
	done
	
	appstream-generator cleanup

	cd -
done

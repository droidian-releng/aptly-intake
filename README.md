
# aptly-intake

aptly intake watches for new packages and imports them using aptly api

aptly repositories have a fairly convoluted pipeline to add each packages

`.changes` file is read by `aptly repo include` and signature is checked to make sure it is signed properly. after that it goes through the repository that is given to the input and adds it to the database.

at this point, the package is still not added to the repository on the filesystem. for changes to take place on the filesystem, we need to make a new snapshot of the repository using `aptly snapshot create`.

aptly-intake for short are a bunch of scripts that do this process automatically.
`aptly-intake-monitor` monitors a directory for changes using inotify and upon file being added, it executes `aptly-intake-import`

`aptly-intake-import` goes through the `.changes` file and and gets enough info to put the package in the correct repository, then it makes a snapshot of the changed repository for it to become available with the new changes.

`aptly-new-snapshot` can be used after each manual change to the repository.

it goes through every single repository and creates a new snapshot. this is useful when we are moving packages across different repositories for various reasons.

# Useful notes
aptly has [a keyring file hardcoded](https://github.com/aptly-dev/aptly/blob/master/pgp/gnupg.go) which needs to be used to save keys for aptly to read it.

To add a key to this database you can use

`gpg --no-default-keyring --keyring /home/aptly-intake-.../gpg/trustedkeys.gpg --import key.key`

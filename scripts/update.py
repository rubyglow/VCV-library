import sys
import os
import glob
import json
import time
import zipfile
import re

import common
import update_modulargrid
import update_cache


TOOLCHAIN_DIR = "../toolchain-v2"
PACKAGES_DIR = "../packages"
SCREENSHOTS_DIR = "../screenshots"
MANIFESTS_DIR = "manifests"
RACK_SYSTEM_DIR = "../Rack-v2"
RACK_USER_DIR = "$HOME/.Rack2"
RACK_USER_PLUGIN_DIR = os.path.join(RACK_USER_DIR, "plugins")

# Update git before continuing
common.system("git pull")
common.system("git submodule sync --quiet")
common.system("git submodule update --init --recursive")

plugin_paths = sys.argv[1:]

# Default to all repos, so all out-of-date repos are built
if not plugin_paths:
	plugin_paths = glob.glob("repos/*")

updated_slugs = set()

for plugin_path in plugin_paths:
	plugin_path = os.path.abspath(plugin_path)
	(plugin_basename, plugin_ext) = os.path.splitext(os.path.basename(plugin_path))
	# Extract manifest from plugin dir or package
	if os.path.isdir(plugin_path):
		manifest_filename = os.path.join(plugin_path, "plugin.json")
		try:
			# Read manifest
			with open(manifest_filename, "r") as f:
				manifest = json.load(f)
		except IOError:
			# Skip plugins without plugin.json
			continue
		slug = manifest['slug']
		version = manifest['version']
	# TODO Extract manifest from .vcvplugin
	elif plugin_ext == ".zip":
		m = re.match(r'^(.*)-(.*?)-(.*?)$', plugin_basename)
		slug = m[1]
		version = m[2]
		arch = m[3]
		# Open ZIP
		z = zipfile.ZipFile(plugin_path)
		# Unzip manifest
		manifest_filename = f"{slug}/plugin.json"
		with z.open(manifest_filename) as f:
			manifest = json.load(f)
		if manifest['slug'] != slug:
			raise Exception(f"Manifest slug does not match filename slug {slug}")
		if manifest['version'] != version:
			raise Exception(f"Manifest slug does not match filename slug {slug}")
	else:
		raise Exception(f"Plugin {plugin_path} is not a valid format")

	# Get library manifest
	library_manifest_filename = os.path.join(MANIFESTS_DIR, f"{slug}.json")

	if os.path.isdir(plugin_path):
		# Check if the library manifest is up to date
		try:
			with open(library_manifest_filename, "r") as f:
				library_manifest = json.load(f)
			if library_manifest and version == library_manifest['version']:
				continue
		except IOError:
			pass

		# Build repo
		print()
		print(f"Building {slug}")
		try:
			common.system(f'cd "{TOOLCHAIN_DIR}" && make plugin-build-clean')
			common.system(f'cd "{TOOLCHAIN_DIR}" && make -j$(nproc) plugin-build PLUGIN_DIR={plugin_path}')
			common.system(f'cp -vi "{TOOLCHAIN_DIR}"/plugin-build/* "{PACKAGES_DIR}"/')
			common.system(f'cp -vi "{TOOLCHAIN_DIR}"/plugin-build/*-lin.vcvplugin "{RACK_USER_PLUGIN_DIR}"')
		except Exception as e:
			print(e)
			print(f"{slug} build failed")
			input()
			continue
		finally:
			common.system(f'cd "{TOOLCHAIN_DIR}" && make plugin-build-clean')

		# Open plugin issue thread
		os.system(f"xdg-open 'https://github.com/VCVRack/library/issues?utf8=%E2%9C%93&q=is%3Aissue+is%3Aopen+in%3Atitle+{slug}' &")

	elif plugin_ext == ".zip":
		# Review manifest for errors
		print(json.dumps(manifest, indent="  "))
		print("Press enter to approve manifest")
		input()

		# Copy package
		package_dest = os.path.join(PACKAGES_DIR, os.path.basename(plugin_path))
		common.system(f'cp "{plugin_path}" "{package_dest}"')
		common.system(f'touch "{package_dest}"')
		if arch == 'lin':
			common.system(f'cp "{plugin_path}" "{RACK_USER_PLUGIN_DIR}"')

	# Copy manifest
	with open(library_manifest_filename, "w") as f:
		json.dump(manifest, f, indent="  ")

	# Delete screenshot cache
	screenshots_dir = os.path.join(SCREENSHOTS_DIR, slug)
	common.system(f'rm -rf "{screenshots_dir}"')

	updated_slugs.add(slug)


if not updated_slugs:
	print("Nothing to build")
	exit(0)

update_cache.update()
update_modulargrid.update()

# Upload data

built_slugs_str = ", ".join(updated_slugs)

print()
print(f"Press enter to launch Rack and test the following packages: {built_slugs_str}")
input()
common.system(f"cd {RACK_SYSTEM_DIR} && ./Rack")
common.system(f"cd {RACK_USER_DIR} && grep 'warn' log.txt || true")
print(f"Press enter to generate screenshots, upload packages, upload screenshots, and commit/push the library repo.")
input()

# Generate screenshots
common.system(f"cd {RACK_SYSTEM_DIR} && ./Rack -t 2")

# Upload packages
common.system("cd ../packages && make upload")

# Upload screenshots
common.system("cd ../screenshots && make -j$(nproc) upload")

# Commit repository
common.system("git add manifests")
common.system("git add manifests-cache.json ModularGrid-VCVLibrary.json")
common.system(f"git commit -m 'Update manifest for {built_slugs_str}'")
common.system("git push")

print()
print(f"Updated {built_slugs_str}")

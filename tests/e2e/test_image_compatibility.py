"""
Verifies that every docker image referenced by bulkrna_paired_unpaired.json
(plus patrickmckeever/bwb_scheduler:latest and patrickmckeever/rnotebook:0.4,
the two other images web/routes.py runs directly) satisfy two conditions:

  1. They're published for both linux/amd64 and linux/arm64.
  2. They don't bundle a Docker Engine/CLI whose default API version would
     trigger the docker daemon error "client version X.YZ is too new.
     Maximum supported API version is 1.43" (i.e. any bundled Docker
     Engine/CLI negotiates down to API <= 1.43). This only matters for
     images (like bwb_scheduler) that themselves invoke `docker` against a
     mounted /var/run/docker.sock.

Both checks are done via the public Docker Hub / Docker Registry HTTP APIs
(tag metadata plus a single small per-image config JSON blob), not by
pulling the images themselves, which are multi-GB.

These are informational checks against third-party images this project
doesn't control. They may legitimately fail (an image may simply not ship
an arm64 build, or may bundle a newer Docker CLI than expected) without that
being a bug in this repo's code -- failures here surface a real
incompatibility to go fix upstream/in the image, not a bug in this test.
"""
import json
import os
import re

import pytest
import requests

pytestmark = pytest.mark.e2e

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKFLOW_JSON_PATH = os.path.join(REPO_ROOT, "bulkrna_paired_unpaired.json")

DOCKER_HUB_TAG_API = "https://hub.docker.com/v2/repositories/{image_name}/tags/{tag}"
REGISTRY_AUTH_URL = "https://auth.docker.io/token"
REGISTRY_API = "https://registry-1.docker.io/v2"

# The client/daemon API version negotiated by a given Docker Engine release.
# Only covers the releases relevant to whether a bundled client would exceed
# API 1.43 (first shipped by Engine 24.0). See
# https://docs.docker.com/engine/release-notes/ and
# https://docs.docker.com/reference/api/engine/#api-version-matrix for the
# full history -- extend this table if a newer/older release needs checking.
ENGINE_VERSION_TO_API_VERSION = {
    (20, 10): (1, 41),
    (23, 0): (1, 42),
    (24, 0): (1, 43),
    (25, 0): (1, 44),
    (26, 0): (1, 45),
    (27, 0): (1, 47),
    (28, 0): (1, 48),
    (28, 1): (1, 49),
    (28, 2): (1, 50),
    (28, 3): (1, 51),
    (29, 0): (1, 52),
}

# The daemon API version quoted in the reported error ("client version 1.52
# is too new. Maximum supported API version is 1.43").
MAX_COMPATIBLE_API_VERSION = (1, 43)

_DOCKER_VERSION_PATTERNS = [
    re.compile(r"docker-ce-cli=(\d+)\.(\d+)\.\d+"),
    re.compile(r"docker-ce=(\d+)\.(\d+)\.\d+"),
    re.compile(r"docker-(\d+)\.(\d+)\.\d+\.tgz"),
    re.compile(r"DOCKER_VERSION[=\s]+(\d+)\.(\d+)\.\d+"),
]


def _load_images_under_test():
    with open(WORKFLOW_JSON_PATH) as fh:
        workflow = json.load(fh)

    nodes = workflow["resolved_workflow"]["Nodes"]
    images = {(node["ImageName"], node["ImageTag"]) for node in nodes.values()}
    images.add(("patrickmckeever/bwb_scheduler", "latest"))
    images.add(("patrickmckeever/rnotebook", "0.4"))
    return sorted(images)


IMAGES = _load_images_under_test()
IMAGE_IDS = [f"{name}:{tag}" for name, tag in IMAGES]


@pytest.fixture(scope="module")
def registry_session():
    session = requests.Session()
    yield session
    session.close()


def _get_tag_metadata(session, image_name, tag):
    url = DOCKER_HUB_TAG_API.format(image_name=image_name, tag=tag)
    response = session.get(url, timeout=30)
    if response.status_code == 404:
        pytest.fail(f"{image_name}:{tag} not found on Docker Hub ({url})")
    response.raise_for_status()
    return response.json()


def _get_registry_token(session, image_name):
    response = session.get(
        REGISTRY_AUTH_URL,
        params={"service": "registry.docker.io", "scope": f"repository:{image_name}:pull"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["token"]


def _get_image_config(session, image_name, tag):
    """
    Fetch the (small, a few KB) image config JSON for one platform's
    manifest -- not the actual image layers/filesystem.
    """
    token = _get_registry_token(session, image_name)
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": ", ".join([
            "application/vnd.docker.distribution.manifest.v2+json",
            "application/vnd.docker.distribution.manifest.list.v2+json",
            "application/vnd.oci.image.manifest.v1+json",
            "application/vnd.oci.image.index.v1+json",
        ]),
    }
    manifest_resp = session.get(
        f"{REGISTRY_API}/{image_name}/manifests/{tag}", headers=headers, timeout=30
    )
    manifest_resp.raise_for_status()
    manifest = manifest_resp.json()

    # Manifest list/index (multi-arch): resolve to one platform's manifest,
    # preferring amd64, before we can read a "config" digest off of it.
    if manifest.get("manifests"):
        platform_manifest = next(
            (m for m in manifest["manifests"] if m.get("platform", {}).get("architecture") == "amd64"),
            manifest["manifests"][0],
        )
        sub_resp = session.get(
            f"{REGISTRY_API}/{image_name}/manifests/{platform_manifest['digest']}",
            headers=headers, timeout=30,
        )
        sub_resp.raise_for_status()
        manifest = sub_resp.json()

    config_digest = manifest["config"]["digest"]
    config_resp = session.get(
        f"{REGISTRY_API}/{image_name}/blobs/{config_digest}", headers=headers, timeout=30
    )
    config_resp.raise_for_status()
    return config_resp.json()


def find_bundled_docker_engine_version(image_config):
    """
    Best-effort: scan the image's build history (the Dockerfile RUN/ENV
    commands baked into its config) for evidence of a pinned Docker
    Engine/CLI version being installed.

    Returns:
        tuple(int, int) or None: (major, minor), or None if the image's
        history shows no pinned Docker Engine/CLI version (e.g. it installs
        an unversioned OS package like "docker.io", or bundles no Docker
        client at all) -- in which case this can't be determined without
        actually pulling and running the image.
    """
    for entry in image_config.get("history", []):
        created_by = entry.get("created_by", "")
        for pattern in _DOCKER_VERSION_PATTERNS:
            match = pattern.search(created_by)
            if match:
                return (int(match.group(1)), int(match.group(2)))
    return None


def max_client_api_version(engine_version):
    """
    Look up the highest client API version a given (major, minor) Docker
    Engine release negotiates by default.

    Returns:
        tuple(int, int) or None: None if engine_version predates every
        entry in ENGINE_VERSION_TO_API_VERSION (table needs extending).
    """
    candidates = {
        release: api_version
        for release, api_version in ENGINE_VERSION_TO_API_VERSION.items()
        if release <= engine_version
    }
    if not candidates:
        return None
    return candidates[max(candidates)]


@pytest.mark.parametrize("image_name,tag", IMAGES, ids=IMAGE_IDS)
def test_image_has_amd64_and_arm64_builds(registry_session, image_name, tag):
    metadata = _get_tag_metadata(registry_session, image_name, tag)
    architectures = {
        image["architecture"]
        for image in metadata.get("images", [])
        if image.get("os") == "linux"
    }

    missing = {"amd64", "arm64"} - architectures
    assert not missing, (
        f"{image_name}:{tag} is missing linux/{'linux/'.join(sorted(missing))} "
        f"build(s); found architectures: {sorted(architectures) or 'none'}"
    )


@pytest.mark.parametrize("image_name,tag", IMAGES, ids=IMAGE_IDS)
def test_image_docker_client_is_api_compatible(registry_session, image_name, tag):
    image_config = _get_image_config(registry_session, image_name, tag)
    engine_version = find_bundled_docker_engine_version(image_config)

    if engine_version is None:
        pytest.skip(
            f"{image_name}:{tag} doesn't pin a Docker Engine/CLI version anywhere "
            "in its build history (e.g. installs an unversioned OS package, or "
            "bundles no Docker client at all); can't determine its client API "
            "version without pulling and running the image."
        )

    client_api_version = max_client_api_version(engine_version)
    assert client_api_version is not None, (
        f"{image_name}:{tag} bundles Docker Engine {engine_version[0]}.{engine_version[1]}, "
        "which isn't covered by ENGINE_VERSION_TO_API_VERSION -- extend that table."
    )

    max_str = f"{MAX_COMPATIBLE_API_VERSION[0]}.{MAX_COMPATIBLE_API_VERSION[1]}"
    client_str = f"{client_api_version[0]}.{client_api_version[1]}"
    assert client_api_version <= MAX_COMPATIBLE_API_VERSION, (
        f"{image_name}:{tag} bundles Docker Engine {engine_version[0]}.{engine_version[1]} "
        f"(client API {client_str}), newer than API {max_str}. Running its bundled "
        f"docker client against an older daemon would fail with "
        f'"client version {client_str} is too new. Maximum supported API version is {max_str}".'
    )

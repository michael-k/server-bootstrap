"""Default constants for Incus VM testing.

INCUS-1 is violated here, deliberately recorded rather than fixed.  Four of
the seven values below are specific to the server-bootstrap project rather
than generic -- ``VM_NAME_PREFIX``, ``IMAGE_PREFIX``,
``DEFAULT_DEBIAN_VERSION`` and ``BASE_IMAGE_PREFIX`` -- and no constructor
parameter, environment variable or configuration hook lets a consuming
repository change any of them.  The three timeout values are generic.  See
specs/incus-tooling/requirements.md for the full enumeration of consumption
sites.

TEST-8: ``IMAGE_PREFIX`` and ``DEFAULT_DEBIAN_VERSION`` name the
``images:debian/13`` stream rather than a fingerprint, which is what keeps
the integration tier following upstream instead of pinning it.
"""


VM_NAME_PREFIX = "bootstrap-test-"

IMAGE_PREFIX = "images:debian/"

DEFAULT_DEBIAN_VERSION = "13"

VM_READY_TIMEOUT_SECONDS = 120

SSH_CONNECT_TIMEOUT_SECONDS = 10

SSH_POLL_INTERVAL_SECONDS = 2

BASE_IMAGE_PREFIX = "bootstrap/internal-base-"

# ADR-0008: SeaweedFS as the S3-compatible object store

- **Status:** Accepted (slice 1, 2026-09-27)
- **Deciders:** project owner, Claude (architecture lead)

**Context.** The architecture named MinIO for documents. During the first `docker compose up`, both `minio/minio` and `minio/mc` failed to pull: the Docker Hub repositories no longer exist and the `quay.io/minio/*` repositories require authentication. MinIO stopped publishing free community images in 2025.

**Decision.** Use SeaweedFS (`chrislusf/seaweedfs:3.99`, Apache-2.0) in single-server mode with its S3 gateway on port 8333. Services talk to it only through the S3 API (`OBJECT_STORE_URL`, access key and secret from `.env`), so any S3-compatible store can replace it. Buckets (`claim-docs`, `grievance-docs`, `ai-corpus`) are created by the owning services at start-up; objects stay private and are reached only through presigned URLs issued after an authorisation check.

**Alternatives.** Garage (S3-compatible, smaller community); LocalStack S3 (test-oriented); building MinIO from source (maintenance burden).

**Consequences.** No web console in the default stack; the S3 contract is unchanged, so code written against boto3 / aioboto3 works against any S3 store.

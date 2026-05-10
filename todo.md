<!--
Copyright 2026 The Apache Software Foundation

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
-->

## URI and archive memory bounds

1. Medium rc_vote_manifest.py:173 reads remote URI bodies without a maximum byte limit. Verification downloads manifests, artifacts, sidecars, and KEYS through this helper, so a large response can cause memory/disk exhaustion before checksum validation.
2. Medium archive_shallow_analysis.py:72 and archive_shallow_analysis.py:239 perform unbounded in-memory archive inspection. A compressed archive with many/large members can amplify into high memory and CPU use during retained inspection.
3. Medium artifact_registration/kinds/maven_repository.py:95 fetches remote Maven repository files with preload_content=True, then stores response.data fully in memory. Large Maven artifacts can be loaded all at once during inventory generation.
4. Medium artifact_registration/kinds/maven_repository.py:435 accumulates prefetched Maven file payloads in a dict[str, bytes]. With many files, total memory use can grow to the full prefetched repository size.
5. Medium artifact_registration/kinds/maven_repository.py:464 reads local Maven repository files entirely into memory for checksumming/cache. Same issue for large local artifacts.
6. Medium verification/secondary/maven_repository_repro.py:150 and verification/secondary/maven_repository_repro.py:154 compare staged and rebuilt Maven files by loading both full payloads into memory.
7. Medium verification/secondary/maven_repository_repro.py:313 reads each ZIP member fully for normalized Maven comparison, similar to archive_shallow_analysis.
8. Medium verification/secondary/file_reproducibility.py:158 compares rebuilt and staged single-file artifacts with read_bytes() on both paths. Large artifacts are loaded twice.
9. Low/Medium source_artifact.py:88 and source_artifact.py:89 read full child stderr temp files into memory. Usually stderr is small, but a noisy or stuck child can grow these files before failure handling.

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
2. Medium verification/secondary/maven_repository.py:154 and verification/secondary/maven_repository_repro.py:150 keep staged Maven repository payloads in a dict[str, bytes] for local reproducibility comparison. With many or large staged files, memory can grow to the staged repository size.

---
title: "Harness shim builtin payload types"
description: "Small runtime payloads used by the harness shim to emulate GitHub and other tools."
---

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

Small runtime payloads used by the harness shim to emulate GitHub and other tools.

Back to the [reference overview](../release-model-schema-reference/).

## Type index

- [HarnessBuiltinGhRefMutationPayload](#harnessbuiltinghrefmutationpayload) — Synthetic GitHub tag-ref mutation payload consumed by the harness shim.

<a id="harnessbuiltinghrefmutationpayload"></a>
### HarnessBuiltinGhRefMutationPayload

Synthetic GitHub tag-ref mutation payload consumed by the harness shim.

- category: `runtime`
- ownership: `runtime-derived`
- schema file: [`harness-builtin-gh-ref-mutation-payload.schema.json`](../../../schemas/harness-builtin-gh-ref-mutation-payload.schema.json)
- audience: `internal`
- stability: `stable`
- file contract: (inner type)

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| <a id="harnessbuiltinghrefmutationpayload-ref"></a>`ref` | str | no | Git ref name observed or created during the related operation. |
| <a id="harnessbuiltinghrefmutationpayload-sha"></a>`sha` | str | no | Git object SHA associated with one synthetic harness GitHub ref mutation payload. |


# AFSIM IR Schema v1

## 1. Goal

This document defines the first formal AFSIM intermediate representation used between natural-language intent parsing and script generation.

The schema is designed for:

- intent extraction from user requests
- grounding to AFSIM platform and component types
- hierarchical script generation
- static verification
- semantic evaluation against benchmark expectations

The machine-readable schema lives in [afsim_ir_schema_v1.json](/C:/Users/28912/Desktop/afsim-script-generator-main/docs/afsim_ir_schema_v1.json:1).

## 2. Design Principles

1. The IR represents scenario intent, not final script syntax.
2. Mission semantics must be explicit in `tasks`, even if the final AFSIM script expresses them through routes, processors, sensors, or weapons.
3. Platform quantity, side, mission, and location must be first-class fields.
4. Grounding is allowed to remain incomplete through `*_hint` fields and `grounding_hints`.
5. The schema should be strict enough for validation but simple enough to author by hand during early experiments.

## 3. Required Core Fields

`schema_version`

- Fixed value: `afsim_ir_v1`

`scenario`

- Scenario metadata.
- Must include `name` and `duration`.

`sides`

- Declares valid force sides such as `blue`, `red`, `neutral`.

`entities`

- The main platform instances or groups.
- This is where platform role, quantity, side, and location binding are expressed.

`tasks`

- Mission intent.
- A task may later map to route logic, processor behavior, command-chain structure, sensor setup, or weapon employment.

## 4. Main Objects

`scenario`

- `name`: stable scenario identifier.
- `description`: optional human summary.
- `duration`: object with `value` and `unit`.
- `domains`: optional tags such as `air`, `surface`, `space`.
- `outputs`: requested products such as `mission_log`, `heatmap`, `event_output`.

`locations`

- Reusable points or areas.
- Use these when a scenario has named launch sites, patrol anchors, defended assets, or orbit anchors.

`routes`

- Abstract motion plans.
- Each route has a `kind` and one or more waypoints.

`platform_templates`

- Optional template layer between high-level entities and grounded AFSIM types.
- Useful when multiple entities share the same component stack.

`components`

- Abstract component catalog grouped by `movers`, `sensors`, `weapons`, `processors`, and `comms`.
- Each item can stay partially grounded through `type_hint`.

`entities`

- The most important operational unit in the IR.
- Required fields:
  - `id`
  - `role`
  - `side`
  - `quantity`
- Common optional fields:
  - `domain`
  - `template_ref`
  - `platform_type_hint`
  - `component_refs`
  - `initial_location_ref`
  - `route_ref`

`tasks`

- Explicit mission representation.
- Required fields:
  - `id`
  - `type`
  - `assignee_refs`
- Optional fields:
  - `target_refs`
  - `location_refs`
  - `parameters`

`constraints`

- Encodes normalization rules that later static checks should enforce.
- Current key fields:
  - `unit_system`
  - `coordinate_format`
  - `required_fields`

`expected_events`

- Event-level success criteria used by evaluation or repair.

`grounding_hints`

- Temporary bridge between user language and grounded AFSIM entities.
- These should shrink as the grounding library improves.

## 5. Minimum Coverage for Task-006

This v1 schema explicitly covers the minimum task requirements:

- Platform: `entities`, `platform_templates`
- Quantity: `entities[].quantity`
- Side: `entities[].side`, `sides`
- Mission: `tasks`
- Location: `locations`, `routes`, `entities[].initial_location_ref`

## 6. Mapping Guidance

Natural language to IR:

- user platform mentions -> `entities.role`, `platform_type_hint`, `grounding_hints`
- user quantity -> `entities.quantity`
- user side or faction -> `entities.side`
- user area, site, start point, patrol anchor -> `locations`
- user motion path or patrol plan -> `routes`
- user requested behavior -> `tasks`

IR to AFSIM script:

- `platform_templates` and `components` -> reusable AFSIM blocks
- `entities` -> `platform_type` and `platform` sections
- `routes` -> `route` blocks or mover parameters
- `tasks` -> processor logic, route selection, weapon setup, comm bindings, and validation expectations

## 7. Validation Rules

At IR validation time:

- every `entity.side` must exist in `sides`
- every `component_ref`, `template_ref`, `location_ref`, `route_ref`, and task ref must resolve
- `quantity` must be >= 1
- `duration`, speed, altitude, and similar numeric values must preserve units
- mission intent must not be hidden only in free text; it must appear in `tasks`

## 8. Non-Goals in v1

- Full one-to-one coverage of every AFSIM command.
- Full grounding catalog of all AFSIM built-in types.
- Guaranteed reversibility from script text back to IR without information loss.

## 9. Relationship to Later Tasks

- Task-007 will define how to parse natural language into this schema.
- Task-008 will replace many `*_hint` fields with grounded entity mappings.
- Task-009 will consume this schema for layer-by-layer script generation.
- Task-010 and later tasks will validate or repair outputs using this schema as the semantic reference.

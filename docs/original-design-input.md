# Bambu Lab X1C Filament Inventory Tracker Design

## Goal

Build a filament inventory application for a Bambu Lab X1C with AMS that tracks every physical spool you own, including spools that are not currently loaded in the four AMS slots.

The application should maintain a rough but useful estimate of remaining filament on each spool and preserve that estimate when spools are removed, stored, and later reinserted.

The AMS should be treated as a temporary spool reader and location, not as the inventory itself.

---

## Core Concept

Each physical spool is a persistent inventory item.

For Bambu RFID spools, the application can use the spool's persistent `tray_uuid` to recognise the same physical spool whenever it is reinserted into the AMS.

Example:

```text
Spool #1
UUID: FB9363D5A52340FB82E133A8CBDBFC31
Material: PLA Basic
Colour: Jade White
Starting weight: 1000 g
Calculated remaining: 817.4 g
AMS remaining estimate: 82%
Location: Stored
```

If the spool is later inserted into AMS slot A4 and the AMS reports the same `tray_uuid`, the application should automatically recognise it as Spool #1 and update its location.

---

## Example Inventory View

```text
MY FILAMENT

PLA Basic
┌─────────────────────────┐
│ Jade White              │
│ ███████████████░░  82%  │
│ 820 g remaining         │
│ Bambu Lab               │
│ AMS A1                  │
└─────────────────────────┘

PLA Matte
┌─────────────────────────┐
│ Charcoal                │
│ █████████░░░░░░░  51%   │
│ 512 g remaining         │
│ Bambu Lab               │
│ Stored                  │
└─────────────────────────┘

PETG HF
┌─────────────────────────┐
│ Black                   │
│ ███░░░░░░░░░░░░░  18%  │
│ 181 g remaining         │
│ Bambu Lab               │
│ Stored                  │
└─────────────────────────┘
```

---

## Inventory Data Model

A spool record should contain at least:

| Field | Description |
|---|---|
| `id` | Internal application spool ID |
| `tray_uuid` | Persistent Bambu RFID spool identifier, where available |
| `brand` | Bambu Lab, eSUN, Polymaker, etc. |
| `material` | PLA, PETG, ABS, ASA, TPU, etc. |
| `subtype` | PLA Basic, PLA Matte, PETG HF, etc. |
| `colour_name` | Human-readable colour name |
| `colour_hex` | Colour value reported by AMS or entered manually |
| `starting_weight_g` | Initial usable filament weight |
| `calculated_remaining_g` | Remaining weight calculated from print usage |
| `ams_remaining_pct` | Latest AMS estimate |
| `location` | Stored, AMS A1, AMS A2, etc. |
| `created_at` | Date the spool was added |
| `last_seen_at` | Last time the spool was detected in the AMS |
| `notes` | Optional user notes |

Example:

```text
Spool #1
UUID: FB9363...
Material: PLA Basic
Colour: White
Remaining: 817 g
Location: AMS A1

Spool #2
UUID: 8AC28D...
Material: PLA Matte
Colour: Black
Remaining: 462 g
Location: Stored
```

---

## AMS Data

The X1C exposes AMS spool information through MQTT.

Useful fields include:

```text
tray_type
tray_sub_brands
tray_color
tray_weight
tray_uuid
tag_uid
remain
```

Example:

```json
{
  "tray_type": "PLA",
  "tray_sub_brands": "PLA Matte",
  "tray_color": "E8AFCFFF",
  "tray_weight": "1000",
  "remain": 76,
  "tray_uuid": "FB9363D5A52340FB82E133A8CBDBFC31"
}
```

The application should listen to printer MQTT status updates and maintain the current mapping between AMS slots and inventory spools.

---

## AMS Slot Mapping

The AMS contains four temporary locations:

```text
AMS A1
AMS A2
AMS A3
AMS A4
```

The application should maintain a mapping such as:

```text
A1 -> tray_uuid FB9363...
A2 -> tray_uuid 729A11...
A3 -> empty
A4 -> tray_uuid 10CC62...
```

The spool remains in the inventory even after its AMS mapping disappears.

---

## Spool Removal

When a spool is removed:

```text
Before:
AMS A1 -> FB9363...

After:
AMS A1 -> empty
```

The application should update:

```text
Spool FB9363...
location = "Stored"
```

It should not delete the spool or reset its estimated remaining weight.

---

## Spool Reinsertion

When a spool is inserted into another AMS slot:

```text
AMS A4 reports:
tray_uuid = FB9363...
```

The application should search the spool inventory.

If the UUID already exists:

```text
Known spool found.

Spool #1
Calculated remaining: 817 g
Location: AMS A4
```

The spool's history and remaining filament estimate should continue from its previous state.

---

## Remaining Filament Estimates

The application should maintain two separate remaining-filament measurements.

### 1. Calculated Remaining Weight

This should be the primary inventory value.

Example:

```text
Starting spool:
1000.0 g

Print 1:
-43.7 g

Print 2:
-81.2 g

Print 3:
-57.7 g

Calculated remaining:
817.4 g
```

### 2. AMS Remaining Percentage

The AMS provides an estimated remaining percentage.

Example:

```text
AMS estimate:
82%
```

The UI can present both:

```text
Estimated remaining

817 g
81.7%

AMS estimate: 82%
```

The AMS estimate should be treated as a secondary sanity check rather than continuously overwriting the calculated value.

---

## Handling Estimate Differences

If calculated usage and AMS estimates diverge significantly, the application can warn the user.

Example:

```text
Calculated remaining: 615 g
AMS estimate: approximately 48%
Expected from AMS: approximately 480 g

Difference: approximately 135 g
```

Possible UI:

```text
Remaining estimate may be inaccurate

[Use calculated]
[Use AMS estimate]
[Enter weight manually]
```

---

## Print Usage Tracking

The slicer's `.gcode.3mf` file contains filament usage estimates per filament.

The relevant metadata can include values such as:

```xml
<filament
    id="1"
    type="PLA"
    color="#FFFFFF"
    used_m="18.42"
    used_g="54.31"
/>
```

The application should parse this metadata for every print.

---

## Single-Filament Print Example

Before printing:

```text
Black PLA Matte
UUID: AAB42...
Remaining: 624.0 g
AMS slot: A2
```

The print metadata says:

```text
Black PLA Matte:
73.6 g
```

After a successful print:

```text
624.0
-73.6
------
550.4 g
```

The spool record becomes:

```text
Black PLA Matte
Remaining: 550.4 g
```

---

## Multi-Filament Print Example

Suppose a print uses:

```text
White PLA     82.3 g
Black PLA     14.7 g
Orange PLA     6.1 g
```

At print start:

```text
A1 -> UUID 11111 -> White PLA
A2 -> UUID 22222 -> Black PLA
A3 -> UUID 33333 -> Orange PLA
```

After the print completes:

```text
UUID 11111   -82.3 g
UUID 22222   -14.7 g
UUID 33333    -6.1 g
```

Each physical spool is updated independently.

---

## Print Lifecycle

A suggested print-tracking workflow:

### Print Start

1. Detect that a print has started through MQTT.
2. Record the current AMS slot-to-spool mapping.
3. Retrieve or locate the `.gcode.3mf`.
4. Parse filament usage from `Metadata/slice_info.config`.
5. Map each sliced filament to the actual physical spool loaded at print start.
6. Create a pending print-usage record.

### Print Completion

If the print completes successfully:

1. Mark the print as completed.
2. Subtract the slicer's estimated `used_g` from each associated spool.
3. Update the spool's calculated remaining weight.
4. Store the usage event in history.

### Cancelled or Failed Prints

Do not subtract the full planned filament amount.

Possible approaches:

- Use print progress to estimate partial usage.
- Use AMS percentage changes as a rough fallback.
- Ask the user whether to accept an estimated deduction.
- Initially, mark failed-print consumption as unresolved and allow manual adjustment.

---

## Spool Usage History

Every spool should have an event history.

Example:

```text
Bambu PLA Matte Black
Spool #14

Starting weight: 1000 g

2026-08-01
Printer detected spool in AMS A2

2026-08-02
Controller Bracket
-34.2 g

2026-08-04
Drone Mount
-81.7 g

2026-08-09
Servo Adapter
-12.5 g

2026-08-10
Removed from AMS

Calculated remaining:
871.6 g
```

This provides traceability and makes manual corrections possible.

---

## Non-Bambu Filament

Third-party spools generally do not contain Bambu RFID tags, so the AMS cannot provide a persistent spool UUID.

These spools need an application-managed identity.

Example:

```text
+ Add spool

Brand: eSUN
Material: PLA+
Colour: Fire Engine Red
Starting weight: 1000 g

[Create]
```

When inserted into the AMS:

```text
AMS A3
PLA+
Red
No RFID identity

Which spool is this?

- eSUN PLA+ Red #14 - 812 g remaining
- eSUN PLA+ Red #27 - 1000 g remaining
- Create new spool
```

Once selected:

```text
AMS A3 -> Inventory spool #14
```

Print usage can then be deducted from that spool normally.

---

## Optional QR or NFC Identification

For third-party filament, a later version could support:

- QR labels
- NFC stickers
- Barcode labels

The application could generate a unique spool ID such as:

```text
SPOOL-000014
```

A label could be attached to the spool.

Scanning it when loading the AMS would immediately identify the physical spool without searching manually.

---

## Suggested Database Tables

### `spools`

```text
id
tray_uuid
brand
material
subtype
colour_name
colour_hex
starting_weight_g
calculated_remaining_g
ams_remaining_pct
location
created_at
last_seen_at
notes
```

### `ams_slots`

```text
printer_id
ams_id
slot_number
spool_id
tray_uuid
updated_at
```

### `prints`

```text
id
printer_id
filename
started_at
completed_at
status
progress_pct
```

### `print_filament_usage`

```text
id
print_id
spool_id
filament_index
planned_usage_g
planned_usage_m
actual_estimated_usage_g
```

### `spool_events`

```text
id
spool_id
event_type
weight_change_g
remaining_g
source
created_at
metadata
```

Possible event types:

```text
created
loaded
unloaded
print_usage
manual_adjustment
ams_reconciliation
refill
discarded
```

---

## Application Architecture

A minimal architecture could be:

```text
Bambu X1C
   |
   | MQTT
   v
Printer Listener
   |
   +-- AMS slot state
   +-- tray_uuid
   +-- material
   +-- colour
   +-- remain %
   +-- print state
   |
   v
Spool Inventory Service
   |
   +-- recognise spools
   +-- handle swaps
   +-- calculate remaining filament
   +-- record spool events
   |
   v
SQLite
   |
   +-- spools
   +-- AMS assignments
   +-- prints
   +-- usage history
   |
   v
Web UI
```

The first version could run entirely on a local machine, NAS, Raspberry Pi, Docker host, or small server.

---

## Suggested Technology Stack

A simple implementation could use:

```text
Backend:
Node.js
MQTT client
SQLite

Frontend:
Vue 3
Quasar

Deployment:
Docker
```

The service would connect directly to the X1C over the local network.

---

## Main Screens

### Inventory

Display all owned spools.

Useful filters:

- Material
- Brand
- Colour
- Remaining percentage
- Location
- Low filament
- Bambu RFID
- Third-party

### AMS

Display the four current AMS slots:

```text
A1  PLA Basic White   817 g
A2  PLA Matte Black   462 g
A3  Empty
A4  PETG HF Red       731 g
```

### Spool Detail

Show:

- Brand
- Material
- Colour
- Starting weight
- Current estimated weight
- AMS estimate
- Current location
- Print history
- Total filament used
- Manual adjustment controls

### Print History

Example:

```text
Drone Controller Mount
2026-08-21

PLA Black
Spool #14
34.2 g

PLA Orange
Spool #8
7.4 g
```

---

## Low-Filament Alerts

The application could support configurable warnings.

Example:

```text
PLA Matte Black
91 g remaining

Low filament
```

Possible thresholds:

```text
Below 20%
Below 200 g
Below 100 g
```

---

## New Spool Workflow

For a new Bambu RFID spool:

1. Insert it into the AMS.
2. Detect an unknown `tray_uuid`.
3. Read its material, colour, type, and starting weight.
4. Create a new spool record automatically.
5. Set its location to the detected AMS slot.

Potential UI:

```text
New filament detected

Bambu PLA Basic
Jade White
1000 g

[Add to inventory]
```

---

## Existing Spool Workflow

When an existing Bambu spool is reinserted:

1. AMS reports its `tray_uuid`.
2. Search the inventory.
3. Find the matching spool.
4. Restore its existing remaining-weight estimate.
5. Update its location.
6. Store a `loaded` event.

No manual selection should be required.

---

## Manual Weight Correction

The user should always be able to override the estimate.

Example:

```text
Current estimate:
417 g

Measured filament:
438 g

[Update]
```

The application should record this as an adjustment rather than rewriting history.

```text
Manual correction
+21 g
New remaining:
438 g
```

---

## Handling Refilled Bambu Spools

A reusable Bambu spool may retain the same physical spool hardware while receiving a new filament refill.

The application should therefore support a "refill" operation.

Example:

```text
Spool UUID: FB9363...

Previous:
PLA Basic Black
23 g remaining

New refill:
PLA Basic Red
1000 g
```

The application should create either:

- a new inventory spool record linked to the same physical RFID identity, or
- a new refill lifecycle under the existing spool identity.

The second option preserves the history of the physical spool while separating filament batches.

---

## Accuracy Expectations

This system should be described as an estimated inventory rather than a precision measurement system.

Potential sources of difference include:

- Purge waste
- Calibration extrusion
- Prime tower usage
- Failed prints
- Cancelled prints
- Manual filament loading and unloading
- Filament cut during AMS swaps
- Slicer estimation differences
- AMS remaining percentage estimation error

For normal successful prints, slicer grams should provide a useful working estimate.

---

## First Version Scope

A practical first release should focus on:

1. Connect to one X1C over local MQTT.
2. Read all four AMS slots.
3. Automatically identify Bambu RFID spools.
4. Maintain a persistent spool inventory.
5. Detect spool insertion and removal.
6. Preserve spool state while stored.
7. Show estimated remaining grams and percentage.
8. Parse filament usage from completed prints.
9. Deduct usage from the correct physical spool.
10. Allow manual spool creation for third-party filament.
11. Allow manual weight corrections.
12. Show basic spool usage history.

Features such as QR codes, NFC tags, cloud sync, multiple printers, analytics, notifications, and advanced failed-print estimation can come later.

---

## Existing Projects Worth Reviewing

Two existing projects are particularly relevant as implementation references.

### Bambu Filament Tracker

Designed around automatically tracking spools that have been inserted into an AMS.

Useful areas to review:

- Spool discovery
- AMS tracking
- Remaining-filament display
- SQLite storage
- Docker deployment

Repository:

https://github.com/EBTEAM3/Bambu-Filament-Tracker

### Bambuddy

A broader Bambu printer management project with spool inventory and print-consumption tracking.

Useful areas to review:

- 3MF filament usage parsing
- AMS slot mapping
- Spool inventory
- Consumption tracking
- Mid-print spool reassignment

Repository:

https://github.com/maziggy/bambuddy

---

## Summary

The core design principle is:

```text
The AMS is not the inventory.

The spool is the inventory item.
```

For Bambu RFID filament, `tray_uuid` provides a persistent identity that allows the application to recognise a spool after it has been removed and later reinserted.

The application combines:

```text
Persistent spool identity
+
AMS slot detection
+
3MF slicer usage estimates
+
AMS remaining percentage
+
Manual corrections
```

This produces an automatically maintained view of all owned filament, including stored spools that are not currently in the AMS.

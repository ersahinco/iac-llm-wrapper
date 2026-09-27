package organisation

# AWS enabled regions must be within the organisation's selected LZA region standard.
assessments := [{"policy_id": "approved-regions", "status": status, "message": message}]

regions := object.get(input.decisions, "enabled_regions", [])
approved := input.references.lza.enabledRegions
outside := sort({region | some region in regions; not region in approved})

status := "not-assessed" if count(regions) == 0

else := "conflict" if count(outside) > 0

else := "passed"

message := "Enabled regions require a usable client answer." if count(regions) == 0

else := sprintf("Regions outside the organisation standard: %v", [outside]) if count(outside) > 0

else := "All stated enabled regions are within the selected organisation standard."

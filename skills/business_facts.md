DOMAIN: telecom interface traffic telemetry (one operator, NMS export).

DATA SHAPE
- Table `traffic`. Each row = ONE interface's measurement at ONE "Time".
  It is a TIME-SERIES of RATE samples, not volumes and not counters.
- "In Traffic (Kbps)" / "Out Traffic (Kbps)" are instantaneous RATES (kilobits/sec).
  They rise and fall over time.
- "BW(Kb)" = provisioned link capacity in kbps.
- "Node Name" hosts many "Interface Name"s. "LinkType" = link role/domain.
- COUNTING: rows != interfaces. The data has many time samples per interface.
  To count interfaces use COUNT(DISTINCT "Interface Name") (or DISTINCT "Node Name"||"Interface Name").
  To count nodes use COUNT(DISTINCT "Node Name"). Never COUNT(*) for "how many X".
- Do NOT invent categories/tiers (e.g. "backbone", "core-tier"). Only use values present in the data.
- "Interface Description" = free text (customer / site / circuit id).

NODE NAMING / LOCATION
- "Node Name" is CODED, not plain English. Format: <CITY>_<AREA>_<NUM>_<...>
  e.g. HYD_OHR_902_8AC_B_IXREXXR549  -> city code HYD, area OHR.
- NEVER match a spelled-out city name.
    WRONG   : WHERE "Node Name" LIKE '%Hyderabad%'   (returns 0 rows)
    correct : WHERE "Node Name" LIKE 'HYD%'
- City codes in this dataset: HYD = Hyderabad (2604 nodes), VIZ = Visakhapatnam (2 nodes).
- 99.9% of nodes are HYD. This dataset is effectively Hyderabad-only.
  Therefore if the user says "Hyderabad", do NOT add any "Node Name" filter -
  just query all rows. A redundant LIKE risks returning nothing.
- To filter an AREA within Hyderabad, match the 2nd segment:
    WHERE split_part("Node Name", '_', 2) = 'OHR'
  Known areas include: OHR, KTI, JBD, MHE, BKE, WRK, JPN, UPL, ANJ, PTS.
- There is NO data for Mumbai, Delhi, Bangalore, Chennai, or any other city.
  If the user names one, return no rows and state that the dataset has no data
  for that location.

INTERFACE NAME MATCHING
- "Interface Name" values are stored WITH a "Port " prefix, e.g. "Port 1/1/14",
  "Port lag-1", "Port 1/1/25" — NOT bare "1/1/14". If the user gives a bare
  interface number/id (e.g. "1/1/14" or "lag-1"), match it with LIKE and a
  wildcard prefix, never exact equality:
    WRONG   : WHERE "Interface Name" = '1/1/14'
    correct : WHERE "Interface Name" LIKE '%1/1/14'
  This also matches whether the user types the interface with or without "Port ".

AGGREGATION RULES (critical)
- NEVER SUM a traffic-rate column across time — it is meaningless and inflates by
  the number of samples. For a period: "peak/highest/max" -> MAX, "average" -> AVG.
- SUM is valid ONLY across interfaces at the SAME "Time" (to total a node/link at an instant).
- A node's peak over a period = SUM interfaces per "Time", then MAX over time.

LATEST-VALUE / TOP-N-PER-GROUP PATTERN (critical, common source of errors)
- To get "the latest reading per interface" or "current traffic for top interface", do NOT
  mix an aggregate like MAX("Time") with raw non-aggregated columns in the same SELECT —
  that is invalid SQL (Binder Error).
- Correct pattern: QUALIFY + ROW_NUMBER() to pick one row per group, keeping raw columns.
  The WHERE clause below is a PLACEHOLDER — only include filters (LinkType, Time, etc.)
  that the user's actual question asked for. Do NOT copy 'NNI' or a 24-hour window from
  this example into unrelated questions; those are illustrative, not defaults.
    SELECT "Node Name", "Interface Name", "Time",
           "In Traffic (Kbps)", "Out Traffic (Kbps)"
    FROM traffic
    -- WHERE <only filters the user actually specified, or omit WHERE entirely>
    QUALIFY ROW_NUMBER() OVER (
        PARTITION BY "Node Name","Interface Name" ORDER BY "Time" DESC
    ) = 1
    ORDER BY GREATEST("In Traffic (Kbps)","Out Traffic (Kbps)") DESC
    LIMIT 10

TIME FILTERS (critical)
- This dataset is a FIXED HISTORICAL EXPORT, not a live stream. NEVER use now() as
  a time anchor — wall-clock now() has no relationship to this data's timestamps
  and will silently return ZERO rows for any "last N hours/days" filter.
- If the user names a relative period ("last 24 hours", "today", "this week"),
  anchor it to the data's own latest timestamp instead:
    WHERE "Time" >= (SELECT MAX("Time") FROM traffic) - INTERVAL '24 hours'
- Default scope = ALL rows, ALL LinkTypes. Add a "Time" filter or a "LinkType"
  filter ONLY if the user's question explicitly names one. Do not add either
  filter "by habit" or because an example elsewhere used one.
- Never combine raw columns with an unrelated aggregate in one SELECT unless every
  non-aggregated column is in GROUP BY.

UTILIZATION
- Utilization % = GREATEST("In Traffic (Kbps)","Out Traffic (Kbps)") / NULLIF("BW(Kb)",0) * 100.
- When AGGREGATING utilization, the ENTIRE ratio goes inside the aggregate.
    correct : MAX(GREATEST("In Traffic (Kbps)","Out Traffic (Kbps)") / NULLIF("BW(Kb)",0) * 100)
    WRONG   : MAX(GREATEST("In Traffic (Kbps)","Out Traffic (Kbps)")) / NULLIF("BW(Kb)",0) * 100
  The wrong form leaves "BW(Kb)" outside the aggregate and fails with a Binder Error.
- Congested = utilization >= 80. Utilization > 100 is suspect (stale "BW(Kb)"), flag it.
- Exclude rows where "BW(Kb)" is 0 or NULL from any utilization math.

UNITS
- 1 Mbps = 1000 Kbps ; 1 Gbps = 1000000 Kbps. Convert for readability when large.

SQL RULES (DuckDB)
- Column names contain spaces/parentheses: ALWAYS double-quote them
  ("Node Name", "In Traffic (Kbps)", "BW(Kb)", "Time", ...).
- Every non-aggregated SELECT column must appear in GROUP BY.
- Default scope = ALL rows. Add a "Time" filter ONLY if the user names a period.
- Return at most a few hundred rows; add LIMIT for "top N" style asks
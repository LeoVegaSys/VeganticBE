import re

from database.db_manager import DatabaseManager
from config import DIP_HIGH_UTIL, DIP_MIN_DROP, QA_ROW_LIMIT


class DipAgent:
    def __init__(self):
        self.dbm = DatabaseManager()
        #TODO Create connection to required database

    def _get_schema_context(self):
        pass

    def _get_dip_sql_query(self, window_hours, linktype_filter, util_filter):
        return f'''WITH data_end AS (SELECT MAX("Time") AS t FROM traffic),
    windowed AS (
        SELECT "Node Name", "Interface Name", "LinkType", "BW(Kb)", "Time",
            "In Traffic (Kbps)", "Out Traffic (Kbps)"
        FROM traffic, data_end
        WHERE "Time" >= data_end.t - INTERVAL '{window_hours} hours'
        {linktype_filter}
    ),
    ranked AS (
        SELECT *, ROW_NUMBER() OVER (
            PARTITION BY "Node Name","Interface Name" ORDER BY "Time" DESC
        ) AS rn
        FROM windowed
    ),
    current AS (SELECT * FROM ranked WHERE rn = 1),
    baseline AS (
        SELECT "Node Name", "Interface Name",
            AVG(GREATEST("In Traffic (Kbps)","Out Traffic (Kbps)")) AS baseline_val
        FROM ranked WHERE rn > 1
        GROUP BY "Node Name", "Interface Name"
    )
    SELECT
        c."Node Name" AS "Node Name",
        c."Interface Name" AS "Interface Name",
        c."LinkType" AS "LinkType",
        c."Time" AS "Latest Time",
        ROUND(GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)"), 2) AS "Current (Kbps)",
        ROUND(b.baseline_val, 2) AS "Baseline (Kbps)",
        ROUND((b.baseline_val - GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)"))
            / NULLIF(b.baseline_val, 0) * 100, 2) AS "Dip %",
        ROUND(GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)")
            / NULLIF(c."BW(Kb)", 0) * 100, 2) AS "Current Utilization %"
    FROM current c
    JOIN baseline b
    ON b."Node Name" = c."Node Name" AND b."Interface Name" = c."Interface Name"
    WHERE b.baseline_val > 0
    AND (b.baseline_val - GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)"))
        / NULLIF(b.baseline_val, 0) * 100 >= ?
    {util_filter}
    ORDER BY "Dip %" DESC
    LIMIT ?'''

    def _extract_limit(self, default=10):
        m = re.search(r'\b(?:limit|top)\s*(\d+)\b', self.qn_low)
        return int(m.group(1)) if m else default
    

    def _extract_linktype(self, valid_linktypes):
        if "all linktype" in self.qn_low or "across all" in self.qn_low:
            return None
        for lt in valid_linktypes:
            if lt and lt.lower() in self.qn_low:
                return lt
        return None
    

    def _extract_pct(self, keyword_pattern, default):
        """Pull an explicit percentage threshold out of the question, e.g.
        'dip of at least 30%' -> 30.0, 'utilization above 90' -> 90.0.
        Falls back to `default` if the question doesn't specify one."""
        m = re.search(rf'{keyword_pattern}\D{{0,15}}?(\d+(?:\.\d+)?)\s*%?', self.qn_low)
        return float(m.group(1)) if m else default


    def _extract_window_hours(self, default=1):
        """Pull a time window out of the question. Defaults to last 1 hour of
        the interface's OWN history (per handoff doc Section 3 default),
        measured from the dataset's own latest timestamp, not wall-clock now()."""
        ql = self.qn_low
        m = re.search(r'last\s*(\d+)\s*hour', ql)
        if m: 
            return int(m.group(1))
        m = re.search(r'last\s*(\d+)\s*day', ql)
        if m: 
            return int(m.group(1)) * 24
        if 'today' in ql: 
            return 24
        if 'this week' in ql: 
            return 24 * 7
        return default

    
    def dip_detect(self, state: dict):
        """Find interfaces whose latest sample dropped sharply vs their own recent
        baseline (baseline = avg of earlier samples within the window, excluding
        the latest sample itself). If the question also mentions utilization/high,
        additionally require the CURRENT sample to be at/above the utilization
        threshold -- this answers "dip before high utilization" style questions:
        recently dipped AND currently running hot.
        All thresholds (drop %, utilization %, window hours) can be overridden by
        the question text; effective values used are returned in `params_used`
        so the caller/frontend can show exactly what filter was applied.
        Returns (sql, cols, rows, ms, params_used)."""
        self.question = state['question']
        self.qn_low = self.question.lower()

        _, lts, _ = self._get_schema_context(con)
        limit = self._extract_limit()
        linktype = self._extract_linktype(valid_linktypes=lts)
        want_high_util = any(w in self.qn_low for w in ("util", "congest", "high", "capacity"))

        min_drop = self._extract_pct(
            keyword_pattern=r'(?:dip|drop|fell|fall)(?:ped)?\s*(?:of|by)?\s*(?:at least|>=)?', 
            default=DIP_MIN_DROP
        )
        high_util = self._extract_pct(
            keyword_pattern=r'(?:util(?:ization)?|congest\w*)\s*(?:of|is|at least|above|>=)?', 
            default=DIP_HIGH_UTIL
        ) if want_high_util else None
        window_hours = self._extract_window_hours()

        linktype_filter = 'AND "LinkType" = ?' if linktype else ""
        util_filter = ('AND GREATEST(c."In Traffic (Kbps)", c."Out Traffic (Kbps)") '
                    '/ NULLIF(c."BW(Kb)", 0) * 100 >= ?') if want_high_util else ""

        # Window is measured from the DATASET's own latest sample, not wall-clock
        # now() -- this dataset is historical/fixed, not a live stream.
        sql = self._get_dip_sql_query(window_hours, linktype_filter, util_filter)

        params = []
        if linktype: params.append(linktype)
        params.append(min_drop)
        if want_high_util: params.append(high_util)
        params.append(limit)

        params_used = {"min_drop_pct": min_drop, "window_hours": window_hours,
                    "linktype": linktype or "ALL", "limit": limit}
        if want_high_util:
            params_used["high_util_pct"] = high_util

        t0 = time.time()
        cur = con.execute(sql, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchmany(QA_ROW_LIMIT)
        data = [{c: (str(v) if hasattr(v, "isoformat") else v) for c, v in zip(cols, r)} for r in rows]
        ms = round((time.time() - t0) * 1000)
        return sql, cols, data, ms, params_used

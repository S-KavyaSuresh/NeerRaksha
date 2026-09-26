import { useDashboard } from '../store/useDashboard'

const km = (v, d = 2) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(d))

const typeList = obj => Object.entries(obj || {})
  .sort((a, b) => b[1] - a[1])
  .map(([k, n]) => `${k} ${n}`)
  .join(' · ')

const int = v => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toLocaleString())

// Population exposure: estimated residential population within the modelled flood
// extent. Never "observed" — a 2020 WorldPop estimate overlaid on model output.
function PopulationMetric({ pop }) {
  if (pop?.status === 'ok') {
    const zero = !pop.population_exposed_estimate
    return <div>
      <span>Estimated population exposed</span>
      <strong>{int(pop.population_exposed_estimate)}</strong>
      <small>{pop.dataset && pop.dataset.includes('WorldPop') ? 'WorldPop 2020' : (pop.dataset || 'WorldPop 2020')}
        {' · '}{pop.resolution || '~100 m'} · DERIVED IMPACT (estimate)
        {zero ? ' — modelled extent did not intersect valid population cells' : ''}</small>
    </div>
  }
  return <div>
    <span>Population exposure</span>
    <strong>—</strong>
    <small>unavailable — {pop?.reason || 'no population dataset connected'}</small>
  </div>
}

// One asset row of the DERIVED IMPACT table. `ok` with affected_count 0 means the
// analysis ran and the modelled extent simply does not reach that asset class —
// that is NOT the same as "unavailable", and is never shown as a bare zero-exposure.
function AssetMetric({ label, section, extra }) {
  const ok = section?.status === 'ok'
  if (!ok) {
    return <div>
      <span>{label}</span>
      <strong>—</strong>
      <small>unavailable{section?.reason ? ` — ${section.reason}` : ''}</small>
    </div>
  }
  const hit = section.affected_count ?? 0
  const total = section.total_in_dataset ?? '—'
  return <div>
    <span>{label}</span>
    <strong>{hit}<small style={{ marginLeft: 6 }}>/ {total}</small></strong>
    <small>{hit === 0 ? 'DERIVED IMPACT — modelled extent does not reach these assets' : `DERIVED IMPACT${extra ? ` · ${extra(section)}` : ''}`}</small>
  </div>
}

export default function ImpactPage() {
  const impact = useDashboard(s => s.backend.impact)
  const engineLabel = useDashboard(s => s.backend.engineLabel)

  if (!impact) {
    return <>
      <p className="prototype-disclaimer">
        <strong>IMPACT ANALYSIS — DERIVED IMPACT.</strong> Counts are a spatial
        intersection of a <strong>MODEL OUTPUT</strong> flood extent with
        <strong> REAL DATA</strong> (OpenStreetMap: roads, buildings, facilities,
        settlements). They are not observed or surveyed damage.
      </p>
      <div className="context-note">
        No modelled flood extent is loaded yet. Run the <strong>Ujjani Dam-Break</strong>
        scenario (section 03) to compute the intersection. Asset counts are not
        shown until a real flood extent is available — unavailable data is never
        reported as zero exposure.
      </div>
    </>
  }

  const src = impact.source || {}
  const engine = src.engine_label || src.engine || engineLabel || 'unknown engine'
  const roads = impact.roads
  const facilities = impact.facilities

  return <>
    <p className="prototype-disclaimer">
      <strong>DERIVED IMPACT</strong> — assets intersecting the modelled inundation
      extent, not assets observed damaged. Validation:{' '}
      <strong>{impact.validation_status || 'NOT PERFORMED'}</strong>.
    </p>

    <dl className="workspace-values">
      <div><dt>Impact derived from</dt><dd>{engine}</dd></div>
      <div><dt>Flood extent</dt><dd>{src.model_classification || impact.data_classification?.flood_extent || 'MODEL OUTPUT'}</dd></div>
      {src.scenario_type && <div><dt>Scenario</dt><dd>{src.scenario_type}</dd></div>}
      {src.scenario_id && <div><dt>Run id</dt><dd>{src.scenario_id}</dd></div>}
      {src.api && <div><dt>Source API</dt><dd style={{ fontSize: 11 }}>{src.api}</dd></div>}
    </dl>

    <div className="impact-metrics">
      <div>
        <span>Flooded area</span>
        <strong>{km(impact.flooded_area_km2, 3)}<small style={{ marginLeft: 6 }}>km²</small></strong>
        <small>MODEL OUTPUT</small>
      </div>
      <PopulationMetric pop={impact.population} />
      <AssetMetric label="Roads" section={roads}
        extra={s => `${km(s.approx_flooded_length_km, 1)} km flooded (${s.length_crs || 'EPSG:32643'})`} />
      <AssetMetric label="Buildings" section={impact.buildings}
        extra={s => `~${km(s.approx_flooded_footprint_km2, 4)} km² footprint`} />
      <AssetMetric label="Facilities" section={facilities} />
      <AssetMetric label="Settlements" section={impact.settlements} />
    </div>

    {roads?.status === 'ok' && roads.affected_count > 0 && Object.keys(roads.by_type || {}).length > 0 && (
      <div className="context-note">Affected road types: {typeList(roads.by_type)}.</div>
    )}

    {facilities?.status === 'ok' && (
      <div className="context-note">
        Facilities by category (dataset): {typeList(facilities.total_by_type)}.
        {facilities.affected_count > 0
          ? <> Affected: {typeList(facilities.by_type)}.</>
          : <> None of the {facilities.total_in_dataset} facilities fall within the modelled extent.</>}
      </div>
    )}

    {impact.settlements?.status === 'ok' && impact.settlements.affected_count > 0 && (
      <div className="context-note">
        Settlement centres within the extent:&nbsp;
        {impact.settlements.affected.map(a => a.name).join(', ')}.
        <br /><small>{impact.settlements.geometry_note}</small>
      </div>
    )}

    {impact.population?.status === 'ok' && (
      <div className="context-note">
        <strong>Population exposure — DERIVED IMPACT (estimate).</strong> Estimated
        residential population within the modelled flood inundation extent, computed
        by overlaying the modelled flood extent on {impact.population.dataset || 'WorldPop 2020 constrained (UN-adjusted)'}
        {' '}({impact.population.resolution || '~100 m'} grid, persons per pixel, {impact.population.crs || 'EPSG:4326'}).
        This is a 2020 population estimate, not the population present at the time of
        any specific past or future event. It represents modelled exposure to the
        modelled inundation extent — not people displaced, people affected,
        casualties, or surveyed damage. Method: {impact.population.method}; {impact.population.nodata_handling}.
        Validation: NOT PERFORMED.
      </div>
    )}

    <dl className="workspace-values" style={{ marginTop: 14 }}>
      <div><dt>Infrastructure</dt><dd>REAL DATA (OpenStreetMap)</dd></div>
      <div><dt>Counts</dt><dd>DERIVED IMPACT — spatial intersection</dd></div>
      <div><dt>Population</dt><dd>{impact.population?.status === 'ok'
        ? `${impact.population.dataset || 'WorldPop 2020'} · DERIVED IMPACT (estimate)`
        : 'OBSERVATION / census — NOT CONNECTED'}</dd></div>
      <div><dt>Validation</dt><dd><strong>{impact.validation_status || 'NOT PERFORMED'}</strong></dd></div>
    </dl>

    <div className="context-note">
      A count of 0 means the analysis ran and the modelled flood extent does not
      reach that asset class — it is not reported as zero exposure, and unavailable
      data is not fabricated.
    </div>
  </>
}

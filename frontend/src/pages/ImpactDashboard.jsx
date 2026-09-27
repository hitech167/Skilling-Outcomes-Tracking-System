import { useCallback, useEffect, useRef, useState } from 'react';
import { api, errorMessage } from '../api/client';
import './ImpactDashboard.css';

// Public, no-login page for external stakeholders (government / CSR reviewers).
// Everything shown comes from GET /api/public/impact-summary, which returns
// programme-wide aggregates only; figures describing fewer than
// `min_group_size` people arrive as null and are shown as "Fewer than N".

const PROJECT_NAME = 'Skilling Outcomes Tracking System';

function pct(value, digits = 1) {
  return `${Number(value).toFixed(digits).replace(/\.0$/, '')}%`;
}

function count(value) {
  return Number(value).toLocaleString('en-IN');
}

function rupees(value) {
  return `₹${Math.round(value).toLocaleString('en-IN')}`;
}

function formatUpdated(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' });
}

function StatTile({ label, value, format = count, note, minGroup, tone }) {
  const suppressed = value === null || value === undefined;
  return (
    <div className="impact-tile">
      <div className="impact-tile-label">{label}</div>
      <div
        className={`impact-tile-value${suppressed ? ' is-suppressed' : ''}${
          !suppressed && tone === 'good' ? ' impact-good' : ''
        }`}
      >
        {suppressed ? '—' : format(value)}
      </div>
      <div className="impact-tile-note">
        {suppressed ? `Not shown: fewer than ${minGroup} records so far` : note}
      </div>
    </div>
  );
}

/**
 * Horizontal bars (one series, one colour) with a value label on every row
 * and a hover / focus tooltip. `rows`: { key, label, value (0..max | null),
 * valueText, tooltip: [lines], muted }.
 */
function BarList({ rows, max, ariaLabel }) {
  const listRef = useRef(null);
  const [tip, setTip] = useState(null);

  const showAt = (row, clientX, clientY) => {
    const box = listRef.current?.getBoundingClientRect();
    if (!box) return;
    setTip({ row, x: clientX - box.left, y: clientY - box.top });
  };

  return (
    <div className="impact-bars-wrap" ref={listRef} onMouseLeave={() => setTip(null)}>
      <ul className="impact-bars" aria-label={ariaLabel}>
        {rows.map((row) => {
          const suppressed = row.value === null || row.value === undefined;
          const width = suppressed || !max ? 0 : Math.max(0, Math.min(100, (row.value / max) * 100));
          return (
            <li
              key={row.key}
              className="impact-bar-row"
              tabIndex={0}
              aria-label={`${row.label}: ${row.valueText}`}
              onMouseMove={(e) => showAt(row, e.clientX, e.clientY)}
              onFocus={(e) => {
                const r = e.currentTarget.getBoundingClientRect();
                showAt(row, r.left + r.width / 2, r.top);
              }}
              onBlur={() => setTip(null)}
            >
              <span className={`impact-bar-label${row.muted ? ' is-muted' : ''}`} title={row.label}>
                {row.label}
              </span>
              <span className="impact-bar-track" aria-hidden="true">
                {!suppressed && <span className="impact-bar-fill" style={{ width: `${width}%` }} />}
              </span>
              <span className={`impact-bar-value${suppressed ? ' is-suppressed' : ''}`}>{row.valueText}</span>
            </li>
          );
        })}
      </ul>
      {tip && (
        <div className="impact-tooltip" style={{ left: tip.x, top: tip.y }} role="presentation">
          <strong>{tip.row.label}</strong>
          {tip.row.tooltip.map((line) => (
            <span key={line} style={{ display: 'block' }}>
              {line}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Loading() {
  return (
    <div className="impact-tiles" aria-busy="true" aria-label="Loading impact figures">
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="impact-skeleton" />
      ))}
    </div>
  );
}

export default function ImpactDashboard() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [copied, setCopied] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    document.title = `Programme Impact — ${PROJECT_NAME}`;
  }, []);

  useEffect(() => {
    let isMounted = true;

    async function fetchSummary() {
      try {
        // Shared: StrictMode (development) runs this mount effect twice
        const res = await api.getShared('/api/public/impact-summary');
        if (isMounted) {
          setData(res);
          setError(null);
        }
      } catch (err) {
        if (isMounted) setError(errorMessage(err, 'Impact figures are unavailable right now.'));
      }
    }

    fetchSummary();

    return () => {
      isMounted = false;
    };
  }, [reloadKey]);

  const retry = () => {
    setError(null);
    setReloadKey((k) => k + 1);
  };

  const share = useCallback(async () => {
    const url = window.location.href;
    try {
      if (navigator.share) {
        await navigator.share({ title: document.title, url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Share sheet dismissed or clipboard blocked — nothing to do
    }
  }, []);

  const k = data?.min_group_size ?? 5;
  const fewer = `Fewer than ${k}`;

  const outcomeRows = data
    ? [
        ['employed', 'Employed'],
        ['self_employed', 'Self-employed'],
        ['apprenticeship', 'Apprenticeship'],
        ['further_education', 'Further education'],
      ].map(([key, label]) => {
        const value = data.outcome_mix[key];
        return {
          key,
          label,
          value,
          valueText: value === null ? fewer : count(value),
          tooltip:
            value === null
              ? [`${fewer} trainees — not shown to protect privacy`]
              : [`${count(value)} trainees`],
        };
      })
    : [];
  const outcomeMax = Math.max(0, ...outcomeRows.map((r) => r.value || 0));

  const districtRows = data
    ? [
        // Highest placement rate first; pooled small districts always last
        ...[...data.districts]
          .sort((a, b) => b.placement_rate - a.placement_rate)
          .map((d) => ({
          key: d.district,
          label: d.district,
          value: d.placement_rate,
          valueText: pct(d.placement_rate, 0),
          tooltip: [
            `${pct(d.placement_rate)} placed`,
            `${count(d.placed_trainees)} of ${count(d.completed_trainings)} completed trainings`,
          ],
        })),
        ...(data.other_districts
          ? [
              {
                key: '__other',
                label: `Other districts (${data.other_districts.districts})`,
                muted: true,
                value: data.other_districts.placement_rate,
                valueText: pct(data.other_districts.placement_rate, 0),
                tooltip: [
                  `${pct(data.other_districts.placement_rate)} placed`,
                  `${count(data.other_districts.placed_trainees)} of ${count(
                    data.other_districts.completed_trainings
                  )} completed trainings`,
                  `Districts with fewer than ${k} completions, combined`,
                ],
              },
            ]
          : []),
      ]
    : [];

  const wages = data?.wages;
  const hasWages = wages && wages.average_initial_monthly !== null && wages.average_latest_monthly !== null;

  return (
    <div className="impact">
      <header className="impact-hero">
        <div className="impact-wrap">
          <div className="impact-topbar">
            <div className="impact-brand">{PROJECT_NAME}</div>
            <button type="button" className="impact-share" onClick={share}>
              {copied ? 'Link copied' : 'Share this page'}
            </button>
          </div>

          <div className="impact-eyebrow">Programme impact</div>
          <h1>From skills training to sustained livelihoods</h1>

          {data && (
            <div className="impact-hero-figure">
              <div className="impact-hero-number">
                {data.placement_rate === null ? '—' : pct(data.placement_rate, 0)}
              </div>
              <p className="impact-hero-caption">
                {data.placement_rate === null ? (
                  <>Placement rate will be published once {k} or more trainees have completed training.</>
                ) : (
                  <>
                    of trainees who completed training are now in{' '}
                    <strong>a job, their own business or an apprenticeship</strong>
                    {data.placed_trainees !== null && (
                      <> — {count(data.placed_trainees)} people so far</>
                    )}
                    .
                  </>
                )}
              </p>
            </div>
          )}
        </div>
      </header>

      <main className="impact-wrap">
        {error ? (
          <div className="impact-state" role="alert">
            <div>{error}</div>
            <button type="button" onClick={retry}>
              Try again
            </button>
          </div>
        ) : !data ? (
          <Loading />
        ) : (
          <>
            <section className="impact-tiles" aria-label="Headline figures">
              <StatTile
                label="Trainees registered"
                value={data.trainees_registered}
                note={`Across ${count(data.districts_covered)} district${data.districts_covered === 1 ? '' : 's'}`}
                minGroup={k}
              />
              <StatTile
                label="Trainings completed"
                value={data.trainings_completed}
                note="Courses finished by registered trainees"
                minGroup={k}
              />
              <StatTile
                label="Employment rate"
                value={data.employment_rate}
                format={(v) => pct(v)}
                note="In wage employment after completing training"
                minGroup={k}
              />
              <StatTile
                label="Job retention"
                value={data.retention_rate}
                format={(v) => pct(v)}
                note="Still in the job at the latest check-in"
                minGroup={k}
              />
              <StatTile
                label="Average wage growth"
                value={wages?.average_growth_percentage}
                format={(v) => `${v >= 0 ? '+' : ''}${pct(v)}`}
                note="From first recorded salary to the latest"
                minGroup={k}
                tone={wages?.average_growth_percentage > 0 ? 'good' : undefined}
              />
              <StatTile
                label="Districts covered"
                value={data.districts_covered}
                note="Where registered trainees live"
                minGroup={k}
              />
            </section>

            <div className="impact-grid">
              <section className="impact-panel" aria-labelledby="impact-outcomes">
                <h2 id="impact-outcomes">Where trainees went</h2>
                <p className="impact-panel-sub">
                  Latest outcome for each completed training, number of trainees.
                </p>
                {outcomeMax === 0 && outcomeRows.every((r) => r.value === 0) ? (
                  <div className="impact-empty">No outcomes recorded yet.</div>
                ) : (
                  <BarList rows={outcomeRows} max={outcomeMax} ariaLabel="Trainees by outcome" />
                )}
              </section>

              <section className="impact-panel" aria-labelledby="impact-wages">
                <h2 id="impact-wages">Earnings after training</h2>
                <p className="impact-panel-sub">
                  Average monthly salary
                  {wages?.employments_measured ? `, across ${count(wages.employments_measured)} jobs` : ''}.
                </p>
                {hasWages ? (
                  <>
                    <div className="impact-wage">
                      <div className="impact-wage-cell">
                        <div className="impact-wage-label">First salary</div>
                        <div className="impact-wage-value">{rupees(wages.average_initial_monthly)}</div>
                      </div>
                      <div className="impact-wage-arrow" aria-hidden="true">
                        →
                      </div>
                      <div className="impact-wage-cell">
                        <div className="impact-wage-label">Latest salary</div>
                        <div className="impact-wage-value">{rupees(wages.average_latest_monthly)}</div>
                      </div>
                    </div>
                    {wages.average_growth_percentage !== null && (
                      <div className="impact-wage-growth">
                        Average growth per job:{' '}
                        <strong className={wages.average_growth_percentage > 0 ? 'impact-good' : undefined}>
                          {wages.average_growth_percentage >= 0 ? '+' : ''}
                          {pct(wages.average_growth_percentage)}
                        </strong>
                      </div>
                    )}
                  </>
                ) : (
                  <div className="impact-empty">
                    Wage figures are published once {k} or more jobs have salary records.
                  </div>
                )}
              </section>

              <section className="impact-panel is-wide" aria-labelledby="impact-districts">
                <h2 id="impact-districts">Placement rate by district</h2>
                <p className="impact-panel-sub">
                  Share of completed trainings that led to a job, own business or apprenticeship.
                  Districts with fewer than {k} completions are combined.
                </p>
                {districtRows.length ? (
                  <BarList rows={districtRows} max={100} ariaLabel="Placement rate by district" />
                ) : (
                  <div className="impact-empty">
                    District figures are published once a district has {k} or more completed trainings.
                  </div>
                )}
              </section>
            </div>

            <p className="impact-method">
              About these figures: they are aggregates only and cover trainees who have given
              consent to be included. Rates use each training&apos;s most recent outcome; salaries
              are monthly equivalents. To protect privacy, no figure describing fewer than {k}{' '}
              people is published.
            </p>
          </>
        )}

        <footer className="impact-footer">
          <span>
            Powered by <strong>{PROJECT_NAME}</strong>
          </span>
          {data?.generated_at && <span>Figures as of {formatUpdated(data.generated_at)}</span>}
        </footer>
      </main>
    </div>
  );
}

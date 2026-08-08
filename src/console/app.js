document.addEventListener('DOMContentLoaded', async () => {
    const worksGrid = document.getElementById('works-grid');
    const evidenceGrid = document.getElementById('evidence-grid');

    // Fetch registered works from the existing /works endpoint
    try {
        const res = await fetch('/works');
        const data = await res.json();
        renderWorks(data.works);
    } catch (e) {
        console.error("Failed to fetch works:", e);
        // Fallback for local development without the server running
        renderWorks([
            {
                work_id: "work-essay-001",
                control_tier: "asserted",
                description: "Foundational essay on technical consent rails."
            },
            {
                work_id: "work-repo-001",
                control_tier: "verified_control",
                description: "Governed fleet of institutional agents administering creative consent."
            }
        ]);
    }

    renderEvidence();

    function renderWorks(works) {
        worksGrid.innerHTML = '';
        works.forEach(work => {
            const card = document.createElement('div');
            card.className = 'work-card';

            const tierClass = `tier-${work.control_tier.replace('_', '-')}`;
            const tierLabel = work.control_tier.replace('_', ' ');

            card.innerHTML = `
                <span class="tier-badge ${tierClass}">${tierLabel}</span>
                <h3 class="work-title">${work.work_id}</h3>
                <p class="work-desc">${work.description}</p>
                <div class="grants-container" id="grants-${work.work_id}">
                    <p style="font-size: 0.8rem; margin-bottom: 0.5rem; color: #5A5755;">Active Grants:</p>
                    <div class="grant-item" id="grant-${work.work_id}-training" style="font-size: 0.85rem; padding: 0.5rem; background: #F5F5F5; border-radius: 4px; margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center;">
                        <span>Scope: <strong>training</strong> (WW, Commercial)</span>
                    </div>
                </div>
                <button class="revoke-btn" onclick="revokeGrant('${work.work_id}', 'training')">Revoke Scope</button>
            `;
            worksGrid.appendChild(card);
        });
    }

    async function renderEvidence() {
        let counts = {
            crawler_access: 'unavailable',
            canary_hit: 'unavailable',
            verbatim_match: 'unavailable',
            redistribution: 'unavailable'
        };

        try {
            const res = await fetch('/evidence-counts');
            if (res.ok) {
                counts = await res.json();
            }
        } catch (e) {
            console.error("Failed to fetch evidence counts:", e);
        }

        // HOD-370: Evidence grouped by class, no totals.
        const classes = [
            { id: 'crawler_access', label: 'Crawler Access', count: counts.crawler_access, note: 'designed-and-instrumented-but-not-yet-observed' },
            { id: 'canary_hit', label: 'Canary Hits', count: counts.canary_hit, note: 'No occurrences yet' },
            { id: 'verbatim_match', label: 'Verbatim Matches', count: counts.verbatim_match, note: 'No occurrences yet' },
            { id: 'redistribution', label: 'Redistribution', count: counts.redistribution, note: 'No occurrences yet' },
            { id: 'inspector_engine', label: 'Inspector Engine', count: counts.inspector_engine || 'unknown', note: 'Active Prompt Inspector engine' }
        ];

        evidenceGrid.innerHTML = '';
        classes.forEach(cls => {
            const card = document.createElement('div');
            card.className = 'evidence-card';
            card.innerHTML = `
                <div class="evidence-class">${cls.label}</div>
                <div class="evidence-count">${cls.count}</div>
                <span class="evidence-note">${cls.note}</span>
            `;
            evidenceGrid.appendChild(card);
        });
    }
});

// Mock Revocation Cascade Animation
function revokeGrant(workId, scope) {
    const grantEl = document.getElementById(`grant-${workId}-${scope}`);
    if (grantEl) {
        // Add strikethrough animation class
        grantEl.classList.add('grant-revoked');
        
        // Change button text
        const btn = grantEl.parentElement.nextElementSibling;
        btn.textContent = 'Preview only';
        btn.disabled = true;
        btn.style.opacity = '0.5';
        btn.style.cursor = 'not-allowed';
        
        // READ-ONLY BY DESIGN — this does NOT call /api/v1/revoke.
        //
        // Revocation requires an artist-principal credential (HMAC over the raw
        // request body, see src/api/auth.py). A static single-page app cannot
        // hold that secret without shipping it to every visitor, so the console
        // deliberately stops at the local rendering and the real cascade is
        // driven by a credentialed caller. Wiring it would need a server-side
        // session exchange this project has not built.
        //
        // The cascade shown below is a LOCAL PREVIEW of what the lattice would
        // reach, not a report of anything that happened.
        console.log(`[preview only — no request sent] Revoking ${scope} on ${workId} would cascade ` +
                    `to the use-types it contains. Nothing has been revoked.`);
    }
}

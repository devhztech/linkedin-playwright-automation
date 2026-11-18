"""Embedded HTTP server providing a realistic LinkedIn-style UI for safe Loom demos."""

from __future__ import annotations

import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

MOCK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>LinkPro Network — People Search</title>
  <style>
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { margin: 0; background: #f4f2ee; color: #191919; }
    header { background: #ffffff; border-bottom: 1px solid #e0dfdc; padding: 12px 32px; display: flex; align-items: center; gap: 20px; position: sticky; top: 0; z-index: 10; }
    .logo { background: #0a66c2; color: #fff; font-weight: 800; font-size: 20px; padding: 6px 10px; border-radius: 6px; }
    .search-box { display: flex; gap: 8px; flex: 1; max-width: 520px; }
    .search-box input { flex: 1; padding: 9px 14px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; background: #edf3f8; }
    .search-box button { background: #0a66c2; color: #fff; border: none; padding: 9px 18px; border-radius: 20px; font-weight: 600; cursor: pointer; }
    .badge-mode { margin-left: auto; background: #e8f5e9; color: #1b5e20; padding: 5px 12px; border-radius: 14px; font-size: 12px; font-weight: 600; }
    main { max-width: 880px; margin: 24px auto; padding: 0 16px; }
    .stats { font-size: 13px; color: #666; margin-bottom: 14px; }
    .card { background: #fff; border: 1px solid #e0dfdc; border-radius: 10px; padding: 18px 20px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    .card h3 { margin: 0 0 4px 0; font-size: 17px; color: #0a66c2; }
    .headline { font-size: 14px; color: #333; margin-bottom: 4px; }
    .meta { font-size: 12px; color: #666; }
    .actions { display: flex; gap: 8px; align-items: center; }
    .btn-outline { border: 1px solid #0a66c2; color: #0a66c2; background: #fff; padding: 7px 16px; border-radius: 20px; font-weight: 600; cursor: pointer; font-size: 13px; }
    .btn-outline:hover { background: #eef3f8; }
    .btn-primary { border: none; background: #0a66c2; color: #fff; padding: 8px 18px; border-radius: 20px; font-weight: 600; cursor: pointer; font-size: 13px; }
    .btn-pending { border: 1px solid #666; color: #666; background: #f3f2ef; padding: 7px 16px; border-radius: 20px; font-weight: 600; font-size: 13px; }
    .modal-backdrop { display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.45); align-items: center; justify-content: center; z-index: 100; }
    .modal-backdrop.open { display: flex; }
    .modal { background: #fff; width: 460px; border-radius: 10px; padding: 22px; box-shadow: 0 12px 32px rgba(0,0,0,0.2); }
    .modal h4 { margin: 0 0 10px 0; font-size: 17px; }
    .modal textarea { width: 100%; height: 100px; padding: 10px; border: 1px solid #ccc; border-radius: 6px; font-size: 14px; resize: vertical; }
    .modal-footer { display: flex; justify-content: flex-end; gap: 10px; margin-top: 14px; }
    .profile-detail { display: none; background: #fff; border: 1px solid #e0dfdc; border-radius: 10px; padding: 24px; margin-bottom: 16px; }
    .profile-detail.open { display: block; }
  </style>
</head>
<body>
  <header>
    <div class="logo">in</div>
    <div class="search-box">
      <input id="search-input" data-testid="search-input" type="text" placeholder="Search people by title, role, or company..." />
      <button id="search-btn" data-testid="search-btn">Search</button>
    </div>
    <div class="badge-mode">SANDBOX DEMO MODE</div>
  </header>

  <main>
    <div id="profile-detail" class="profile-detail" data-testid="profile-detail">
      <button class="btn-outline" onclick="closeProfile()" style="margin-bottom:12px;">← Back to results</button>
      <h2 id="detail-name" style="margin:0 0 6px 0;"></h2>
      <div id="detail-headline" class="headline"></div>
      <div id="detail-company" class="meta" style="margin-bottom:12px;"></div>
      <p id="detail-bio" style="font-size:14px; line-height:1.5; color:#222;"></p>
    </div>

    <div class="stats" id="stats-bar">Showing all 6 verified B2B profiles</div>
    <div id="results-container"></div>
  </main>

  <div id="connect-modal" class="modal-backdrop" data-testid="connect-modal">
    <div class="modal">
      <h4 id="modal-title">Invite to connect</h4>
      <p style="font-size:13px; color:#555; margin-top:0;">Add a personalized note to increase acceptance rate:</p>
      <textarea id="connect-note" data-testid="connect-note" placeholder="Write a personalized note..."></textarea>
      <div class="modal-footer">
        <button class="btn-outline" onclick="closeModal()">Cancel</button>
        <button id="send-invite-btn" data-testid="send-invite-btn" class="btn-primary" onclick="submitInvite()">Send invitation</button>
      </div>
    </div>
  </div>

  <script>
    const LEADS = [
      { id: "alex-chen-saas", name: "Alex Chen", headline: "Co-Founder & CEO | B2B SaaS & AI Workflows", company: "FlowStack AI", location: "San Francisco, CA", bio: "Building automated revenue operations for mid-market SaaS teams. Previously scaled engineering at CloudPulse (acquired 2023)." },
      { id: "sarah-miller-growth", name: "Sarah Miller", headline: "SaaS Founder & Head of Growth", company: "MetricPulse", location: "Austin, TX", bio: "Helping PLG startups turn trial users into enterprise accounts. Always exploring browser automation and outbound tooling." },
      { id: "david-kim-cto", name: "David Kim", headline: "Founder & CTO | Developer Infrastructure", company: "DeployGrid", location: "New York, NY", bio: "10+ years building distributed systems, CI/CD pipelines, and automated QA infrastructure." },
      { id: "priya-nair-ops", name: "Priya Nair", headline: "VP of Operations & SaaS Founder", company: "ScaleOps Labs", location: "Seattle, WA", bio: "Streamlining B2B lead enrichment, CRM hygiene, and multi-channel outbound workflows." },
      { id: "marcus-vance-rev", name: "Marcus Vance", headline: "SaaS Founder | Outbound & GTM Automation", company: "PipeCraft", location: "Chicago, IL", bio: "Focused on ethical, rate-limited GTM automation and high-intent B2B prospecting." },
      { id: "elena-rostova-eng", name: "Elena Rostova", headline: "Engineering Lead | Browser & Data Pipelines", company: "CrawlForge", location: "Boston, MA", bio: "Architecting resilient Playwright & Chromium scraping clusters with proxy rotation." }
    ];

    let activeLeadId = null;
    const connectedIds = new Set();

    function render(filterText = "") {
      const q = filterText.trim().toLowerCase();
      const filtered = LEADS.filter(l =>
        !q ||
        l.name.toLowerCase().includes(q) ||
        l.headline.toLowerCase().includes(q) ||
        l.company.toLowerCase().includes(q)
      );
      document.getElementById("stats-bar").textContent = `Showing ${filtered.length} profile(s) for "${filterText || 'All'}"`;
      const container = document.getElementById("results-container");
      container.innerHTML = filtered.map(lead => {
        const isPending = connectedIds.has(lead.id);
        return `
          <div class="card" data-testid="lead-card" data-lead-id="${lead.id}">
            <div>
              <h3 data-testid="lead-name">${lead.name}</h3>
              <div class="headline" data-testid="lead-headline">${lead.headline}</div>
              <div class="meta" data-testid="lead-company">${lead.company} · ${lead.location}</div>
            </div>
            <div class="actions">
              <button class="btn-outline" data-testid="view-profile-btn" onclick="openProfile('${lead.id}')">View Profile</button>
              ${isPending
                ? `<button class="btn-pending" data-testid="pending-btn" disabled>Pending ✓</button>`
                : `<button class="btn-primary" data-testid="connect-btn" onclick="openModal('${lead.id}')">Connect</button>`
              }
            </div>
          </div>
        `;
      }).join("");
    }

    function openProfile(id) {
      const lead = LEADS.find(l => l.id === id);
      if (!lead) return;
      document.getElementById("detail-name").textContent = lead.name;
      document.getElementById("detail-headline").textContent = lead.headline;
      document.getElementById("detail-company").textContent = `${lead.company} · ${lead.location}`;
      document.getElementById("detail-bio").textContent = lead.bio;
      document.getElementById("profile-detail").classList.add("open");
    }

    function closeProfile() {
      document.getElementById("profile-detail").classList.remove("open");
    }

    function openModal(id) {
      activeLeadId = id;
      const lead = LEADS.find(l => l.id === id);
      document.getElementById("modal-title").textContent = `Connect with ${lead.name}`;
      document.getElementById("connect-note").value = "";
      document.getElementById("connect-modal").classList.add("open");
    }

    function closeModal() {
      document.getElementById("connect-modal").classList.remove("open");
      activeLeadId = null;
    }

    function submitInvite() {
      if (activeLeadId) {
        connectedIds.add(activeLeadId);
      }
      closeModal();
      render(document.getElementById("search-input").value);
    }

    document.getElementById("search-btn").addEventListener("click", () => {
      render(document.getElementById("search-input").value);
    });

    render();
  </script>
</body>
</html>
"""


class _MockHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        _ = parse_qs(parsed.query)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(MOCK_HTML.encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return  # Keep terminal output clean for Rich UI


class MockLinkedInServer:
    """Context manager that runs the local mock server in a background daemon thread."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765) -> None:
        self.host = host
        self.port = port
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def __enter__(self) -> "MockLinkedInServer":
        self._server = ThreadingHTTPServer((self.host, self.port), _MockHandler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()


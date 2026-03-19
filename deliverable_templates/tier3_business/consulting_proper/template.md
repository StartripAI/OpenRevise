<style>
  :root {
    --mc-blue: #051c2c;
    --mc-light-blue: #00609c;
    --mc-gray: #f2f2f2;
    --mc-accent: #00a9e0;
    --text-main: #333333;
  }
  .report-wrapper {
    font-family: 'Helvetica Neue', Arial, sans-serif;
    color: var(--text-main);
    line-height: 1.6;
    max-width: 1000px;
    margin: 0 auto;
  }
  .hero-header {
    background: linear-gradient(135deg, var(--mc-blue) 0%, var(--mc-light-blue) 100%);
    color: white;
    padding: 3rem 2rem;
    border-radius: 8px 8px 0 0;
    margin-bottom: 2rem;
  }
  .hero-header h1 {
    color: white;
    font-size: 2.5rem;
    margin-bottom: 0.5rem;
    font-weight: 300;
  }
  .meta-grid {
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 1rem;
    margin-top: 2rem;
    font-size: 0.9rem;
    opacity: 0.9;
  }
  .exec-summary {
    background-color: var(--mc-gray);
    border-left: 6px solid var(--mc-accent);
    padding: 1.5rem;
    margin: 2rem 0;
    border-radius: 0 8px 8px 0;
  }
  h2 {
    color: var(--mc-blue);
    border-bottom: 2px solid var(--mc-gray);
    padding-bottom: 0.5rem;
    margin-top: 2.5rem;
    font-weight: 600;
  }
  .insight-box {
    border: 1px solid #e0e0e0;
    border-radius: 6px;
    padding: 1rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 4px rgba(0,0,0,0.02);
  }
  .insight-box h4 {
    color: var(--mc-light-blue);
    margin-top: 0;
  }
  .badge {
    display: inline-block;
    padding: 0.25em 0.6em;
    font-size: 0.75em;
    font-weight: 700;
    border-radius: 0.25rem;
    color: white;
  }
  .badge-high { background-color: #d9534f; }
  .badge-med { background-color: #f0ad4e; }
  .badge-low { background-color: #5cb85c; }
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 1.5rem 0;
  }
  th {
    background-color: var(--mc-blue);
    color: white;
    padding: 12px;
    text-align: left;
  }
  td {
    padding: 12px;
    border-bottom: 1px solid #ddd;
  }
</style>

<div class="report-wrapper">

<div class="hero-header">
  <div style="text-transform: uppercase; letter-spacing: 2px; font-size: 0.8rem; margin-bottom: 1rem;">Strategic Analysis & Advisory</div>
  <h1>[CLIENT/PROJECT NAME]</h1>
  <div style="font-size: 1.2rem; font-weight: 300;">Strategic Roadmap and Value Creation Plan 2026</div>
  
  <div class="meta-grid">
    <div><strong>Prepared For:</strong><br>[Client Stakeholder]</div>
    <div><strong>Date:</strong><br>[Date]</div>
    <div><strong>Confidentiality:</strong><br><span style="color: #ffcccc;">Strictly Confidential</span></div>
  </div>
</div>

<div class="exec-summary">
  <h3 style="margin-top: 0; color: var(--mc-blue);">Executive Summary</h3>
  <p>[1-paragraph punchy synthesis. What is the core problem? What is the $ impact? What is our definitive recommendation?]</p>
  <ul>
    <li><strong>The Core Challenge:</strong> [1 sentence]</li>
    <li><strong>The Untapped Value:</strong> [1 sentence with metrics]</li>
    <li><strong>The Key Moves:</strong> [1 sentence on the strategic pivot]</li>
  </ul>
</div>

## 1. Context & Objective (The "Situation")

[A crisp, 2-paragraph overview of the macroeconomic and industry tailwinds/headwinds creating urgency for the client.]

## 2. Current State Diagnosis (The "Complication")

[Data-driven breakdown of operational bottlenecks. Avoid fluff—use hard numbers.]

### Value Chain Friction Points
<div style="display: flex; gap: 1rem;">
  <div class="insight-box" style="flex: 1;">
    <h4>1. Top-Line Growth</h4>
    <p>[Insight on sales/GTM limitations, supported by data.]</p>
  </div>
  <div class="insight-box" style="flex: 1;">
    <h4>2. Margin Pressure</h4>
    <p>[Insight on COGS/OPEX bloat.]</p>
  </div>
  <div class="insight-box" style="flex: 1;">
    <h4>3. Capital Efficiency</h4>
    <p>[Insight on working capital, tech debt.]</p>
  </div>
</div>

## 3. Strategic Options & Financial Modeling

[Evaluation of 3 distinct paths forward.]

| Strategic Initiative | CapEx Required ($M) | Expected Revenue Uplift | NPV @ 10% | Risk Profile | Recommendation |
|----------------------|---------------------|-------------------------|-----------|--------------|----------------|
| **Option A: [Name]** | | | | <span class="badge badge-high">High</span> | ❌ |
| **Option B: [Name]** | | | | <span class="badge badge-low">Low</span> | ❌ |
| **Option C: [Name]** | | | | <span class="badge badge-med">Medium</span> | ✅ |

### Value Waterfall Analysis
```mermaid
pie title Expected EBITDA Contribution by Initiative
    "Pricing Optimization" : 35
    "Supply Chain Restructuring" : 45
    "GenAI Agent Automation" : 20
```

## 4. Implementation Blueprint

### 100-Day Execution Roadmap

```mermaid
gantt
    title Strategy Execution Timeline (First 100 Days)
    dateFormat  YYYY-MM-DD
    section Phase 1: Mobilize
    [Action 1]           :a1, 2026-04-01, 15d
    [Action 2]           :a2, after a1, 20d
    section Phase 2: Execute
    [Action 3]           :a3, after a2, 30d
    [Action 4]           :a4, after a3, 35d
```

## 5. Risk Assessment & Mitigation

| Critical Risk | Impact | Mitigation Strategy | Owner |
|---------------|--------|---------------------|-------|
| [Risk 1]      | Severity: [High] | [Concrete containment plan] | [CXO Title] |

</div>

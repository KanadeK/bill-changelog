# Research and non-duplication record

Research date: **2026-08-08 America/Los_Angeles** (some API timestamps were 2026-08-09 UTC).

This document records why Bill Changelog was selected. It does not claim that proving the absence
of every private, unindexed, deleted, or future project is possible. The defensible claim is:

> No directly matching public repository was found under the documented searches: a local,
> deterministic tool that compares consecutive consumer bill statements at line-item level and
> exports evidence-linked, tamper-verifiable change reports.

## 1. Existing-project exclusion

The local `D:\我的\GitHub` workspace was inventoried before selection. README or package
descriptions were extracted from roughly one hundred directories. Already-covered domains include:

- repository, agent, CI, release, API, test, dependency, and incident tooling;
- CSV/Parquet analysis, privacy scanning, spreadsheet/BOQ checking, and document preflight;
- game feel, save migration, replay desync, shaders, loot tables, and control maps;
- household allergens, laundry, smart-home automation, PC wiring, power, Wi-Fi, and manuals;
- asset licensing, caption QA, media selection, print PDFs, maps, and educational tools.

The closest prior consumer-document project is ManualCare, which converts equipment manuals into
maintenance plans and calendars. Bill Changelog instead compares monetary line items across time,
calculates cost impact, and builds a billing evidence pack. No local project performs that job.

## 2. GitHub gap searches

The GitHub CLI was authenticated as `KanadeK`. Exact phrase searches were run against repository
names and descriptions, sorted by stars:

| Query | Public matches |
|---|---:|
| `"bill statement" diff in:name,description` | 0 |
| `"recurring bill" comparison in:name,description` | 0 |
| `"bill drift" in:name,description` | 0 |
| `"statement diff" billing in:name,description` | 0 |
| `"bill analyzer" consumer in:name,description` | 0 |
| `"invoice diff" in:name,description` | 3 |

The three `invoice diff` matches were inspected rather than counted as automatically different:

- [Jean-Eudes/invoice-diff](https://github.com/Jean-Eudes/invoice-diff) was a 2012 empty IntelliJ
  repository with no implementation.
- [LopezAngarita/invoice-diff-explainations](https://github.com/LopezAngarita/invoice-diff-explainations)
  sends three uploaded business documents to OpenAI and parses a returned Markdown table.
- [hk206/invoice-diff-checker](https://github.com/hk206/invoice-diff-checker) sends PDFs to Gemini
  to reconcile the cover total against detail totals within an invoice.

None compares consecutive consumer bills locally or emits page/line evidence and a verifiable
artifact bundle.

Broader topic searches showed that adjacent categories are crowded:

- [Actual Budget](https://github.com/actualbudget/actual), Firefly III, and similar tools manage
  budgets and transactions.
- [nobill](https://nobill.app/) scans sources for subscriptions and cancellation opportunities.
- [warranty-tracker topic](https://github.com/topics/warranty-tracker) includes return-window and
  warranty dashboards.
- [invoice-ocr topic](https://github.com/topics/invoice-ocr) focuses on document extraction and
  accounts-payable workflows.

That led to a deliberate boundary: no budget ledger, subscription cancellation, receipt return
tracker, OCR service, or invoice-generation features.

## 3. Rejected name collision

The first candidate name, `BillDrift`, appeared available under initial exact feature queries. A
separate global name search found [markheydon/billdrift-web](https://github.com/markheydon/billdrift-web),
an unfinished B2B reconciliation tool for Giacom supplier billing and Stripe subscriptions. Even
though the use case differs, the name and “billing drift” concept were too close, so the name was
rejected.

Final checks for `Bill Changelog`:

- `"bill-changelog" in:name`: 0 GitHub repositories;
- `KanadeK/bill-changelog`: repository did not exist;
- PyPI `billchangelog`: HTTP 404 before publication.

## 4. Demand signals

Primary consumer guidance supports the underlying problem:

- The US FTC warns that automatic renewals may cost more than the previous period, especially when
  a promotional rate ends, and advises consumers to verify the expected amount:
  [FTC auto-renewal guidance](https://consumer.ftc.gov/articles/getting-and-out-free-trials-auto-renewals-and-negative-option-subscriptions).
- FCC truth-in-billing material describes “cramming” as unauthorized charges on telecom bills and
  emphasizes clearly identified new providers and understandable charge descriptions:
  [FCC cramming requirements](https://docs.fcc.gov/public/attachments/DA-13-1140A1_Rcd.pdf).
- Ofcom maintains a billing-and-charges complaint path and directs consumers to explain the issue to
  the provider, make a formal complaint, and retain escalation evidence:
  [Ofcom billing and charges](https://www.ofcom.org.uk/make-a-complaint/complain-about-mobile-phone-or-internet-services/billing-and-charges?language=en).

The available Agent Reach Bilibili search backend also returned concrete Chinese-language interest:

- [“自动续费忘关被扣钱？”](https://www.bilibili.com/video/BV1nKXYYYEjE) — about 319k plays in the
  retrieved result;
- [“中国移动…我要每个月结余，话费账单减扣增加详情”](https://www.bilibili.com/video/BV1EG4y1u7ZT)
  — a direct request for month-over-month additions and deductions;
- [“套餐39.6元，这个月却扣了69.5元”](https://www.bilibili.com/video/BV1KJTd6pEWS) — a concrete
  “read the bill carefully” scenario.

Counts are snapshots from the search response, not durable popularity guarantees.

## 5. Research limitations

Agent Reach's environment check found GitHub CLI, Bilibili search API, V2EX public API, RSS, and
Jina Reader available. Exa, Reddit, X/Twitter, and Xiaohongshu backends were unavailable, so no
claims are made about direct coverage of those platforms. GitHub's search rate limit was hit once;
the limit status was rechecked and the exact searches were rerun successfully afterward.

Star potential is a product hypothesis, never a guarantee. The hypothesis rests on:

- a one-sentence mental model (“git diff for bills”);
- a broad, recurring consumer pain rather than a narrow developer workflow;
- local privacy with no accounts or API keys;
- shareable HTML evidence and a visible fictional demo;
- an extensible contribution surface for provider profiles and locale fixtures.

# Pitch Deck – Hackerthorn Project

---

## 1. Title Slide
**Project:** Hackerthorn – AI‑Powered Hospitality Review Analytics
**Tagline:** Turning Guest Reviews into Actionable Insights with Multilingual NLP
**Team:** Elliot Hacks (Lead Engineer), Open‑Source Community
**Date:** June 2 2026

---

## 2. The Problem
- Hotels receive thousands of guest reviews across platforms (Booking.com, TripAdvisor, local sites).
- Reviews are in **multiple languages** (English, Swahili, other African languages).
- Manual analysis is slow, error‑prone, and fails to surface actionable trends.
- Existing sentiment tools focus on English only, missing critical local sentiment.

---

## 3. The Solution
**Hackerthorn** provides a fully‑automated pipeline that:
1. Detects the review language (English, Swahili, others).
2. Scores sentiment using a hybrid approach:
   - **AfriSenti transformer** for Swahili (offline, privacy‑first).
   - Heuristic lexicons for fast batch processing.
3. Extracts topics, key phrases, and aspect scores (cleanliness, staff, wifi, etc.).
4. Stores structured results in a searchable database.
5. Offers a **chat‑based query engine** for on‑demand analytics.

---

## 4. Market Opportunity
- **Hospitality analytics market:** > $3 B globally, growing 12% YoY.
- **Emerging markets in East Africa** have a 30% higher proportion of Swahili‑language reviews.
- Hotels of all sizes need multilingual insight to improve guest experience and online reputation.

---

## 5. Product Highlights
| Feature | Benefit |
|---|---|
| **Multilingual NLP** (English + Swahili) | Captures sentiment from the majority of African reviews |
| **Offline transformer** | No API cost, privacy‑preserving, works in low‑bandwidth environments |
| **Heuristic fallback** | Guarantees processing even when the model fails |
| **Aspect‑level scoring** | Pinpoint problem areas (cleanliness, staff, wifi, etc.) |
| **Chat query engine** | Business users ask natural‑language questions without SQL |
| **Batch + on‑demand** | Efficient nightly batch jobs + instant LLM‑driven queries |

---

## 6. Technology Stack
- **Python 3.12**, Django ORM for data persistence
- **AfriSenti transformer** (XLM‑RoBERTa base) loaded from local safetensors
- **Heuristic lexicons** for Swahili/English sentiment and aspect keywords
- **LLM service** (Claude) for on‑demand topic extraction and chat queries
- **Docker** container for reproducible deployment
- **GitHub Actions** CI/CD with automated model validation

---

## 7. Traction & Validation
- **Proof of concept** on a dataset of 20 k reviews (90% Swahili/English mix).
- **Accuracy:** Swahili sentiment F1 = 0.89 vs. baseline lexicon 0.71.
- **Speed:** Batch processing of 10 k reviews in < 2 minutes on a single‑core VM.
- **Community:** 12 contributors, model checkpoint hosted on HuggingFace.

---

## 8. Roadmap
| Q3 2026 | Q4 2026 | Q1 2027 |
|---|---|---|
| Add **Kiswahili‑only** model fine‑tuned on hospitality data | Deploy **SaaS** multi‑tenant version | Build **visual dashboard** with real‑time KPI widgets |
| Enable **additional African languages** (Amharic, Yoruba) | Integrate **review‑to‑action workflow** (automated alerts) |
| Publish **Python SDK** for easy embedding |

---

## 9. Business Model
- **Open‑source core** (model, pipeline) – free for community use.
- **Enterprise SaaS tier** – hosted, secure, with custom language models and SLA.
- **Per‑review pricing** for on‑demand LLM queries (e.g., $0.001 per query).

---

## 10. The Team
- **Elliot Hacks** – Full‑stack Engineer, NLP specialist, open‑source maintainer.
- **Community Contributors** – 12 developers, 4 data scientists, 2 domain experts.
- **Advisors** – Hospitality consultants, African language experts.

---

## 11. Ask
- **Funding:** $750 k (seed) to accelerate multi‑language support, SaaS infrastructure, and sales outreach.
- **Partnerships:** Hotel chains in East Africa for pilot programs.
- **Talents:** NLP engineers, DevOps, product designers.

---

*Prepared by the Hackerthorn team – turning raw guest voices into data‑driven hospitality excellence.*
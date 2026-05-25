# Pricing Model Proposal

## Pricing Philosophy

The platform's costs are driven by **compute time** (model inference), **storage** (MinIO), and **API requests** (infrastructure overhead). We charge primarily on compute consumption since that's the dominant cost.

---

## Cost Model

### Compute Costs (Self-Hosted)

| Resource | Cost (Cloud VM) | Notes |
|----------|-----------------|-------|
| GPU VM (A10G) | $1.50/hr | For production inference |
| CPU VM (8-core) | $0.30/hr | API + queue + DB |
| Storage (SSD) | $0.10/GB/mo | MinIO + PostgreSQL |
| Bandwidth | $0.09/GB | Egress for result downloads |

### Per-Request Cost Breakdown

| Modality | Compute Time (GPU) | Compute Cost | Storage per Request | Total Cost |
|----------|-------------------|--------------|-----------------------|------------|
| Image (512x512) | 5s | $0.0021 | 0.5 MB × $0.0001 | **$0.0022** |
| Voice STT (1 min audio) | 3s | $0.0013 | 0.01 MB | **$0.0013** |
| Voice TTS (100 words) | 2s | $0.0008 | 0.3 MB | **$0.0009** |

---

## Pricing Tiers

### Tier 1: Hobby — $0/month

| Feature | Limit |
|---------|-------|
| API requests | 100/month |
| Rate limit | 10 RPM |
| Image generation | 50 images |
| Voice STT | 30 minutes audio |
| Voice TTS | 20 requests |
| Storage retention | 24 hours |
| Support | Community |

**Cost to serve:** $0.22/user/month  
**Margin:** Loss leader (acquisition)

---

### Tier 2: Pro — $49/month

| Feature | Limit |
|---------|-------|
| API requests | 10,000/month |
| Rate limit | 60 RPM |
| Image generation | 5,000 images |
| Voice STT | 500 minutes audio |
| Voice TTS | 2,000 requests |
| Storage retention | 7 days |
| API keys | 5 |
| Webhooks | ✅ |
| Priority queue | ✅ |
| Support | Email (24h SLA) |

**Cost to serve:** $18.50/user/month  
**Gross margin:** 62%  
**Break-even:** ~380 users

**Unit economics at 10K requests:**
| Component | Cost |
|-----------|------|
| Compute (GPU) | $12.00 |
| Storage | $2.50 |
| Infrastructure | $4.00 |
| **Total** | **$18.50** |

---

### Tier 3: Enterprise — $499/month

| Feature | Limit |
|---------|-------|
| API requests | 100,000/month |
| Rate limit | 300 RPM |
| All modalities | Unlimited within quota |
| Storage retention | 30 days |
| API keys | Unlimited |
| Webhooks | ✅ |
| Priority queue | ✅ (dedicated) |
| Dedicated GPU | Optional ($200/mo add-on) |
| SLA | 99.9% uptime |
| Support | Slack + priority email (4h SLA) |

**Cost to serve:** $185/user/month  
**Gross margin:** 63%  
**Break-even:** ~20 users

**Unit economics at 100K requests:**
| Component | Cost |
|-----------|------|
| Compute (GPU) | $120.00 |
| Storage | $25.00 |
| Infrastructure | $40.00 |
| **Total** | **$185.00** |

---

## Usage-Based Overages

Beyond tier limits, charge per unit:

| Modality | Overage Price |
|----------|---------------|
| Image | $0.005/image |
| Voice STT | $0.006/minute |
| Voice TTS | $0.003/request |
| Storage | $0.15/GB/month |

---

## Revenue Projections

### Year 1 Targets

| Metric | Month 3 | Month 6 | Month 12 |
|--------|---------|---------|----------|
| Hobby users | 500 | 2,000 | 5,000 |
| Pro users | 20 | 100 | 400 |
| Enterprise | 2 | 5 | 15 |
| **MRR** | **$1,978** | **$7,395** | **$27,085** |
| Gross margin | 55% | 60% | 65% |

### Key Metrics to Track

1. **Cost per request** — monitor compute efficiency
2. **Conversion rate** — Hobby → Pro (target: 4%)
3. **Churn rate** — Pro monthly (target: <5%)
4. **GPU utilization** — target >60% for cost efficiency
5. **P95 latency** — directly impacts customer satisfaction

---

## Competitive Positioning

| Feature | LenAI | Replicate | RunPod |
|---------|-------|-----------|--------|
| Self-hosted option | ✅ | ❌ | ❌ |
| Fixed monthly pricing | ✅ | ❌ (pay-per-use) | Partial |
| Multi-modal API | ✅ | ❌ (per-model) | ❌ |
| Webhook delivery | ✅ | ✅ | ❌ |
| On-prem deployment | ✅ | ❌ | ❌ |
| Starting price | $0 | $0.0023/run | $0.39/hr |

**Our edge:** Unified API across modalities, self-hosted deployment option, predictable pricing, and webhook-first architecture for production integrations.

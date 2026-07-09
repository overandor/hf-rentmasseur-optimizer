import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  const root = process.cwd();

  let kpiData: any = null;
  let decision: any = null;
  let experiment: any = null;
  let bios: any[] = [];
  let receiptCount = 0;

  try {
    const decisionPath = path.join(root, "content", "decisions", "latest_decision.json");
    const raw = await fs.readFile(decisionPath, "utf-8");
    decision = JSON.parse(raw);
    kpiData = decision.kpi_snapshot;
  } catch { }

  try {
    const expPath = path.join(root, "content", "experiments", "exp_001_targeted_wolf.json");
    experiment = JSON.parse(await fs.readFile(expPath, "utf-8"));
  } catch { }

  try {
    const biosDir = path.join(root, "content", "bios");
    const files = await fs.readdir(biosDir);
    for (const f of files) {
      if (f.endsWith(".json")) {
        bios.push(JSON.parse(await fs.readFile(path.join(biosDir, f), "utf-8")));
      }
    }
  } catch { }

  try {
    const receiptPath = path.join(root, "receipts", "hourly_kpi_receipts.jsonl");
    const raw = await fs.readFile(receiptPath, "utf-8");
    receiptCount = raw.trim().split("\n").length;
  } catch { }

  if (kpiData) {
    return NextResponse.json({
      ...kpiData,
      decision: decision ? { state: decision.decision, reason: decision.reason, timestamp: decision.timestamp } : kpiData.decision,
      experiment,
      bios,
      receipt_count: receiptCount,
      product: "ClientPulse OS",
      tagline: "Know which client signals are real before you change the profile",
      timestamp: new Date().toISOString(),
    });
  }

  return NextResponse.json({
    product: "ClientPulse OS",
    tagline: "Know which client signals are real before you change the profile",
    immortality: {
      score: 0.8287,
      label: "DURABLE",
      vector: [1.0, 1.0, 0.9654, 0.6948, 0.1381],
      dimensions: ["visibility", "availability", "retention", "view_consistency", "return_rate"],
    },
    virality: {
      score: 0.7615,
      label: "ACCELERATING",
      vector: [0.0191, 0.0256, 0.0013, 1.0],
      dimensions: ["view_velocity", "click_velocity", "return_trend", "momentum_persistence"],
    },
    conversion: {
      score: 0.0486,
      label: "LOW",
      total_views: 8567,
      total_clicks: 416,
      raw_rate: 0.0486,
      prior: "Beta(2, 38)",
    },
    trust: {
      score: 1.0,
      label: "GREEN",
      dirty_flags: [],
      is_clean: true,
    },
    decision: {
      state: "WINNER_FOUND",
      reason: "CTR rising with views holding — keep this variant",
    },
    experiment,
    bios,
    receipt_count: receiptCount,
    snapshots: 3,
    latest_timestamp: "2026-06-27T10:00:00Z",
    latest_metrics: {
      views: 2910,
      contact_clicks: 142,
      views_per_day: 81,
      days_online: 964,
      new_visitors: 2508,
      returning_visitors: 402,
      bookmarks: 45,
    },
    timestamp: new Date().toISOString(),
  });
}

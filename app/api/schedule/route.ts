import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

export async function GET() {
  const root = process.cwd();
  let genome: any = null;
  let schedule: any = null;

  try {
    const genomePath = path.join(root, "content", "schedule", "evolved_genome.json");
    genome = JSON.parse(await fs.readFile(genomePath, "utf-8"));
  } catch {}

  try {
    const schedulePath = path.join(root, "content", "schedule", "today_schedule.json");
    schedule = JSON.parse(await fs.readFile(schedulePath, "utf-8"));
  } catch {}

  const now = new Date();
  const programs = schedule?.programs?.map((p: any) => {
    const wake = new Date(p.wake_time);
    const retire = new Date(p.retire_time);
    let status = p.status;
    let countdown = null;

    if (now >= wake && now < retire) {
      status = "active";
    } else if (now >= retire) {
      status = "retired";
    } else {
      status = "dormant";
      const diff = wake.getTime() - now.getTime();
      const hours = Math.floor(diff / 3600000);
      const minutes = Math.floor((diff % 3600000) / 60000);
      const seconds = Math.floor((diff % 60000) / 1000);
      countdown = `${hours}h ${minutes}m ${seconds}s`;
    }

    return { ...p, status, countdown, wake_time: p.wake_time, retire_time: p.retire_time };
  }) || [];

  const activeCount = programs.filter((p: any) => p.status === "active").length;
  const dormantCount = programs.filter((p: any) => p.status === "dormant").length;
  const retiredCount = programs.filter((p: any) => p.status === "retired").length;

  const hourlyDensity = Array(24).fill(0);
  for (const p of programs) {
    const wake = new Date(p.wake_time);
    hourlyDensity[wake.getUTCHours()]++;
  }

  return NextResponse.json({
    genome: genome
      ? {
          generation: genome.generation,
          fitness: genome.fitness,
          genes: genome.genes,
        }
      : null,
    programs,
    summary: {
      total: programs.length,
      active: activeCount,
      dormant: dormantCount,
      retired: retiredCount,
    },
    hourly_density: hourlyDensity,
    generated: schedule?.generated || now.toISOString(),
    timestamp: now.toISOString(),
  });
}

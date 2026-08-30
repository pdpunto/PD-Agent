import { rmSync } from "node:fs";

export default function globalTeardown() {
  const root = process.env.PD_AGENT_I12_D_TEMP_ROOT;
  if (root) rmSync(root, { recursive: true, force: true });
}

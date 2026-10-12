/**
 * scripts/seed-admin.ts
 *
 * Safe development CLI script to bootstrap or reset the test Admin account.
 * Usage:
 *   npx tsx scripts/seed-admin.ts [email] [password]
 */

const targetUrl = process.env.WORKER_URL || "http://127.0.0.1:8787/api/dev/seed-admin";
const email = process.argv[2] || process.env.ADMIN_DEFAULT_EMAIL || "admin@example.com";
const password = process.argv[3] || process.env.ADMIN_DEFAULT_PASSWORD || "AdminDemo12345!Secure";

async function main() {
  console.log("==================================================");
  console.log("   Bootstrap / Reset Local Test Admin Account     ");
  console.log("==================================================");
  console.log(`Target Worker URL : ${targetUrl}`);
  console.log(`Admin Email       : ${email}`);
  console.log(`Role              : admin`);
  console.log("--------------------------------------------------");

  try {
    const res = await fetch(targetUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ email, password }),
    });

    const data = (await res.json()) as { success?: boolean; message?: string; error?: string };

    if (!res.ok) {
      console.error(`❌ Error (${res.status}): ${data.error || data.message || "Failed to seed admin"}`);
      process.exit(1);
    }

    console.log("✅ Success!");
    console.log(`Message: ${data.message}`);
    console.log("\nCredentials to log in:");
    console.log(`Email    : ${email}`);
    console.log(`Password : ${password}`);
    console.log("==================================================");
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    console.error("❌ Failed to reach local Worker server:", msg);
    console.log("\nTip: Make sure the worker is running first with: npm run dev:worker");
    console.log("Or click 'Create / Reset Local Admin' in the Login page UI.\n");
    process.exit(1);
  }
}

main();

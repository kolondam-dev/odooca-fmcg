// Generate a Railway Start Command from the audited gateway files.
// Uses an official nginx image; never fetches code or credentials at runtime.
import { readFileSync } from "node:fs";
const names = [
    "staging-locations.conf",
    "railway-gateway.conf.template",
    "railway-gateway-entrypoint.sh",
];
const commands = ["mkdir -p /opt/gateway"];
for (const name of names) {
    const payload = readFileSync(
        new URL("../hosting/" + name, import.meta.url),
    ).toString("base64");
    commands.push(
        "printf %s " + payload + " | base64 -d > /opt/gateway/" + name,
    );
}
commands.push("exec /bin/sh /opt/gateway/railway-gateway-entrypoint.sh");
console.log("/bin/sh -c '" + commands.join(" && ") + "'");

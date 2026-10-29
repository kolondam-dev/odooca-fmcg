import { test } from "node:test";
import assert from "node:assert/strict";
import { mkdtemp, mkdir, writeFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { once } from "node:events";
import { staticServer } from "./server.mjs";
test("hosting scopes routes, API and cache correctly", async () => {
    const dir = await mkdtemp(join(tmpdir(), "pwa-host-"));
    await mkdir(join(dir, "assets"));
    for (const [file, content] of [
        ["index.html", "<h1>shell</h1>"],
        ["sw.js", "// worker"],
        ["assets/app-hash.js", "// bundle"],
        [".env", "private"],
    ])
        await writeFile(join(dir, file), content);
    const server = staticServer(dir).listen(0, "127.0.0.1");
    await once(server, "listening");
    const base = `http://127.0.0.1:${server.address().port}`;
    try {
        let r = await fetch(base + "/", { redirect: "manual" });
        assert.equal(r.status, 302);
        assert.equal(r.headers.get("location"), "/field/");
        r = await fetch(base + "/healthz");
        assert.equal(await r.text(), "ok");
        r = await fetch(base + "/field/sales");
        assert.equal(await r.text(), "<h1>shell</h1>");
        assert.equal(r.headers.get("cache-control"), "no-store");
        r = await fetch(base + "/field/sw.js");
        assert.equal(r.headers.get("cache-control"), "no-store");
        assert.equal(r.headers.get("service-worker-allowed"), null);
        r = await fetch(base + "/field/assets/app-hash.js");
        assert.match(r.headers.get("cache-control"), /immutable/);
        assert.match(r.headers.get("content-type"), /javascript/);
        assert.equal(r.headers.get("x-content-type-options"), "nosniff");
        r = await fetch(base + "/field/", { method: "HEAD" });
        assert.equal(await r.text(), "");
        for (const path of [
            "/field/assets/missing.js",
            "/field/missing.png",
            "/field/.env",
            "/field/%2e%2e%2f.env",
            "/field/%5c.env",
            "/outside",
            "/field/%00",
        ])
            assert.equal((await fetch(base + path)).status, 404, path);
        assert.equal((await fetch(base + "/api/v1/me/bootstrap")).status, 503);
        assert.equal(
            (await fetch(base + "/field/", { method: "POST" })).status,
            405,
        );
    } finally {
        await new Promise((done) => server.close(done));
        await rm(dir, { recursive: true, force: true });
    }
});

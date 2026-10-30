import { defineConfig } from "vite";
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { resolve } from "node:path";

export default defineConfig(({ mode }) => {
    if (!["demo", "production", "test", "staging"].includes(mode))
        throw new Error("Unsupported mode");
    const demo = mode === "demo";
    const target = demo ? "demo" : mode === "staging" ? "staging" : "live";
    return {
        base: "/field/",
        define: {
            __DEMO__: JSON.stringify(demo),
            __READ_ONLY__: JSON.stringify(mode === "staging"),
        },
        build: {
            outDir: `dist/${target}`,
            emptyOutDir: true,
            sourcemap: false,
        },
        plugins: [
            {
                name: "field-offline-shell",
                closeBundle() {
                    const dir = resolve(`dist/${target}`);
                    const files = readdirSync(dir, { recursive: true }).filter(
                        (x): x is string =>
                            typeof x === "string" &&
                            /\.(js|css|woff2|html|svg|png|webmanifest)$/.test(
                                x,
                            ),
                    );
                    const digest = createHash("sha256");
                    for (const file of files)
                        digest.update(readFileSync(resolve(dir, file)));
                    const name = `fmcg-field-${target}-${digest.digest("hex").slice(0, 12)}`;
                    const urls = files.map(
                        (x) => "/field/" + x.replaceAll("\\", "/"),
                    );
                    writeFileSync(
                        resolve(dir, "sw.js"),
                        `
${
    target === "staging"
        ? "self.addEventListener('install',()=>self.skipWaiting()); self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('fmcg-field-')).map(k=>caches.delete(k)))).then(()=>self.registration.unregister())));"
        : `const CACHE=${JSON.stringify(name)}, URLS=${JSON.stringify(urls)};
self.addEventListener('install',e=>e.waitUntil(caches.open(CACHE).then(c=>c.addAll(URLS))));
self.addEventListener('activate',e=>e.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>k.startsWith('fmcg-field-')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));
self.addEventListener('fetch',e=>{const u=new URL(e.request.url);if(e.request.method!=='GET'||u.origin!==self.location.origin||!u.pathname.startsWith('/field/'))return;
if(e.request.mode==='navigate'){e.respondWith(fetch(e.request).catch(()=>caches.match('/field/index.html')));return;}
if(URLS.includes(u.pathname))e.respondWith(caches.match(u.pathname,{ignoreVary:true}).then(r=>r||fetch(e.request)));});`
}
`,
                    );
                    writeFileSync(
                        resolve(dir, "build-info.json"),
                        JSON.stringify({
                            mode: target,
                            cache: name,
                            assets: urls,
                        }),
                    );
                },
            },
        ],
    };
});

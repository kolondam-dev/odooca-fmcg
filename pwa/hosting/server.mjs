import { createServer } from "node:http";
import { readFile, stat } from "node:fs/promises";
import { resolve, sep, extname } from "node:path";
import { pathToFileURL } from "node:url";
const mime = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json",
    ".webmanifest": "application/manifest+json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".woff2": "font/woff2",
    ".txt": "text/plain; charset=utf-8",
};
export function staticServer(directory) {
    const root = resolve(directory);
    return createServer(async (req, res) => {
        res.setHeader("X-Content-Type-Options", "nosniff");
        res.setHeader("Referrer-Policy", "strict-origin-when-cross-origin");
        res.setHeader("Cache-Control", "no-store");
        const finish = (status, text) => {
            res.writeHead(status, {
                "Content-Type": "text/plain; charset=utf-8",
            });
            res.end(req.method === "HEAD" ? undefined : text);
        };
        if (!["GET", "HEAD"].includes(req.method)) {
            res.setHeader("Allow", "GET, HEAD");
            return finish(405, "Method not allowed");
        }
        let path;
        try {
            path = decodeURIComponent(
                new URL(req.url, "http://localhost").pathname,
            );
        } catch {
            return finish(400, "Invalid path");
        }
        if (path === "/healthz") return finish(200, "ok");
        if (path === "/" || path === "/field") {
            res.writeHead(302, { Location: "/field/" });
            return res.end();
        }
        if (path.startsWith("/api/"))
            return finish(503, "Odoo API integration unavailable");
        if (
            !path.startsWith("/field/") ||
            path.includes("\\") ||
            path.includes("\0")
        )
            return finish(404, "Not found");
        const relative = path.slice("/field/".length);
        if (relative.split("/").some((part) => part.startsWith(".")))
            return finish(404, "Not found");
        let file = resolve(root, relative || "index.html");
        if (!file.startsWith(root + sep)) return finish(404, "Not found");
        try {
            if (!(await stat(file)).isFile()) return finish(404, "Not found");
        } catch {
            // Deep links may use the shell; missing assets/API never receive HTML.
            if (extname(relative) || relative.startsWith("assets/"))
                return finish(404, "Not found");
            file = resolve(root, "index.html");
        }
        try {
            const content = await readFile(file);
            res.setHeader(
                "Content-Type",
                mime[extname(file)] || "application/octet-stream",
            );
            res.setHeader("Content-Length", content.length);
            if (relative.startsWith("assets/"))
                res.setHeader(
                    "Cache-Control",
                    "public, max-age=31536000, immutable",
                );
            res.writeHead(200);
            res.end(req.method === "HEAD" ? undefined : content);
        } catch {
            finish(500, "Static build unavailable");
        }
    });
}
if (
    process.argv[1] &&
    import.meta.url === pathToFileURL(resolve(process.argv[1])).href
) {
    const port = Number(process.env.PORT || 8080);
    if (!Number.isInteger(port) || port < 1 || port > 65535)
        throw new Error("Invalid PORT");
    staticServer(process.env.PWA_DIST || "dist/live").listen(port, "0.0.0.0");
}

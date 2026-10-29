// Disposable transport fixture for gateway smoke, never an authentication service.
import { createServer } from "node:http";
createServer((req, res) => {
    res.setHeader("Cache-Control", "no-store, private");
    if (req.url === "/web/login?redirect=%2Ffield%2F") {
        res.writeHead(302, {
            "Set-Cookie":
                "session_id=gateway-test; Path=/; HttpOnly; SameSite=Lax",
            Location: "/field/",
        });
        return res.end();
    }
    if (
        req.url === "/api/v1/me/bootstrap" ||
        req.url === "/api/v1/sync/snapshot"
    ) {
        res.setHeader("Content-Type", "application/json");
        if (!req.headers.cookie?.includes("session_id=gateway-test")) {
            res.writeHead(401);
            return res.end(JSON.stringify({ error: "not_authenticated" }));
        }
        return res.end(
            JSON.stringify({
                fixture: true,
                path: req.url,
                host: req.headers.host,
                proto: req.headers["x-forwarded-proto"],
            }),
        );
    }
    res.writeHead(404);
    res.end();
}).listen(8069, "0.0.0.0");

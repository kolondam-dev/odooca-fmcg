import {
    sha256,
    evidenceBinding,
    validateEvidenceTime,
    type EvidenceReference,
} from "./evidence-package";
import type { Evidence } from "../storage/store";
function canvas(width: number, height: number) {
    const c = document.createElement("canvas");
    c.width = width;
    c.height = height;
    const ctx = c.getContext("2d");
    if (!ctx) throw new Error("Pratinjau bukti tidak tersedia.");
    return { c, ctx };
}
async function encode(c: HTMLCanvasElement, type: string, max: number) {
    const blob = await new Promise<Blob | null>((r) => c.toBlob(r, type, 0.76));
    if (!blob || blob.size > max)
        throw new Error(
            "Paket foto terlalu besar. Ambil ulang dengan resolusi lebih kecil.",
        );
    return blob;
}
export async function compressEvidence(file: File): Promise<Blob> {
    if (
        !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
        file.size > 12 * 1024 * 1024
    )
        throw new Error("Pilih JPEG/PNG/WebP maksimal 12 MB.");
    const bitmap = await createImageBitmap(file);
    try {
        if (
            !bitmap.width ||
            !bitmap.height ||
            bitmap.width * bitmap.height > 40_000_000
        )
            throw new Error(
                "Resolusi foto terlalu besar. Maksimal 40 megapiksel.",
            );
        const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
        const { c, ctx } = canvas(
            Math.max(1, Math.round(bitmap.width * scale)),
            Math.max(1, Math.round(bitmap.height * scale)),
        );
        ctx.drawImage(bitmap, 0, 0, c.width, c.height);
        return await encode(c, "image/jpeg", 1024 * 1024);
    } finally {
        bitmap.close();
    }
}
export async function renderEvidencePackage(
    photo: Blob,
    owner: string,
    ref: EvidenceReference,
    selectedAt: string,
    fixSampledAt: string,
    relaxed = false,
    caption?: { company: string; employee: string; address: string },
): Promise<Evidence> {
    validateEvidenceTime(ref, selectedAt, fixSampledAt, relaxed);
    const bitmap = await createImageBitmap(photo);
    const width = Math.max(640, bitmap.width),
        height = bitmap.height;
    const bannerHeight = caption ? 220 : 126;
    const { c, ctx } = canvas(width, height + bannerHeight);
    try {
        ctx.fillStyle = "#fff";
        ctx.fillRect(0, 0, width, height);
        ctx.drawImage(
            bitmap,
            (width - bitmap.width) / 2,
            0,
            bitmap.width,
            bitmap.height,
        );
    } finally {
        bitmap.close();
    }
    ctx.fillStyle = "#102746";
    ctx.fillRect(0, height, width, bannerHeight);
    ctx.fillStyle = "#fff";
    ctx.font = "16px sans-serif";
    const when = new Date(ref.capturedAt).toLocaleString("id-ID", {
        timeZone: "Asia/Makassar",
    });
    const coordinates = `${ref.latitude.toFixed(6)}, ${ref.longitude.toFixed(6)} | +/- ${ref.accuracy.toFixed(1)} m`;
    ctx.fillText(
        "SIMULASI | Waktu pencatatan perangkat (WITA)",
        16,
        height + 25,
    );
    ctx.fillText(when, 16, height + 50);
    ctx.fillText(coordinates, 16, height + 75);
    ctx.font = "12px sans-serif";
    ctx.fillText(
        "Waktu shutter/kamera asli dan mock GPS tidak diverifikasi",
        16,
        height + 101,
    );
    if (caption) {
        ctx.fillStyle = "#102746";
        ctx.fillRect(0, height, width, bannerHeight);
        ctx.fillStyle = "#fff";
        ctx.font = "bold 18px sans-serif";
        ctx.fillText(caption.company, 16, height + 28, width - 32);
        ctx.font = "16px sans-serif";
        ctx.fillText(caption.employee, 16, height + 56, width - 32);
        ctx.fillText(
            `${when} WITA · waktu perangkat`,
            16,
            height + 84,
            width - 32,
        );
        const words = caption.address.split(/\s+/);
        let line = "",
            y = height + 112;
        for (const word of words) {
            if (ctx.measureText(`${line} ${word}`).width > width - 32 && line) {
                ctx.fillText(line, 16, y, width - 32);
                y += 22;
                line = word;
            } else line = `${line} ${word}`.trim();
        }
        ctx.fillText(line, 16, Math.min(y, height + 156), width - 32);
        ctx.fillText(coordinates, 16, height + 184, width - 32);
        ctx.font = "12px sans-serif";
        ctx.fillText(
            "Bukti lokal · alamat diisi pengguna · belum diverifikasi server",
            16,
            height + 207,
            width - 32,
        );
    }
    const blob = await encode(c, "image/jpeg", 1024 * 1024);
    const { c: m, ctx: g } = canvas(480, 320);
    g.fillStyle = "#edf3f9";
    g.fillRect(0, 0, 480, 320);
    g.strokeStyle = "#c7d6e5";
    g.lineWidth = 1;
    for (let x = 40; x < 480; x += 40) {
        g.beginPath();
        g.moveTo(x, 40);
        g.lineTo(x, 256);
        g.stroke();
    }
    for (let y = 56; y <= 256; y += 40) {
        g.beginPath();
        g.moveTo(20, y);
        g.lineTo(460, y);
        g.stroke();
    }
    // Metric local grid only: no invented roads, tiles or basemap attribution.
    const extent = Math.max(100, Math.ceil(ref.accuracy / 100) * 100),
        pixelsPerMeter = 100 / extent;
    g.fillStyle = "#2f76bc22";
    g.strokeStyle = "#2f76bc";
    g.beginPath();
    g.arc(240, 148, Math.max(2, ref.accuracy * pixelsPerMeter), 0, Math.PI * 2);
    g.fill();
    g.stroke();
    g.fillStyle = "#c03f5f";
    g.beginPath();
    g.arc(240, 148, 7, 0, Math.PI * 2);
    g.fill();
    g.fillStyle = "#102746";
    g.font = "bold 16px sans-serif";
    g.fillText("PINPOINT SIMULASI - TANPA BASEMAP", 15, 25);
    g.font = "14px sans-serif";
    g.fillText("N / UTARA", 370, 55);
    g.fillText("+", 237, 121);
    g.strokeStyle = "#102746";
    g.beginPath();
    g.moveTo(30, 235);
    g.lineTo(130, 235);
    g.stroke();
    g.fillText(`${extent} m`, 35, 225);
    g.font = "12px sans-serif";
    g.fillText(coordinates, 15, 278);
    g.fillText(`${when} WITA`, 15, 299);
    const map = await encode(m, "image/png", 128 * 1024);
    const source = {
        version: 1 as const,
        kind: "simulation_grid" as const,
        ...(__DEMO__ && relaxed ? { demo_unrestricted: true as const } : {}),
        selectedAt,
        fixSampledAt,
        photoSha256: await sha256(blob),
        mapSha256: await sha256(map),
    };
    const row: Evidence = {
        owner,
        key: `${owner}:${ref.id}`,
        blob,
        capturedAt: ref.capturedAt,
        latitude: ref.latitude,
        longitude: ref.longitude,
        accuracy: ref.accuracy,
        mapStatus: "pending",
    };
    return {
        ...row,
        visual: {
            ...source,
            bindingSha256: await sha256(evidenceBinding(row, source)),
            map,
        },
    };
}

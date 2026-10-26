import { useEffect, useState } from "preact/hooks";
import { FieldStore } from "../storage/store";
import { Icon } from "./Icon";
export interface EvidenceRef {
    id: string;
    latitude: number;
    longitude: number;
    accuracy: number;
    capturedAt: string;
}
async function compress(file: File): Promise<Blob> {
    if (
        !["image/jpeg", "image/png", "image/webp"].includes(file.type) ||
        file.size > 12 * 1024 * 1024
    )
        throw new Error("Pilih JPEG/PNG/WebP maksimal 12 MB.");
    const bitmap = await createImageBitmap(file);
    const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Kamera tidak tersedia.");
    context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    bitmap.close();
    const blob = await new Promise<Blob | null>((resolve) =>
        canvas.toBlob(resolve, "image/jpeg", 0.76),
    );
    if (!blob || blob.size > 1024 * 1024)
        throw new Error(
            "Foto masih terlalu besar. Ambil ulang dengan resolusi lebih kecil.",
        );
    return blob;
}
export function EvidenceCapture({
    store,
    owner,
    onChange,
}: {
    store: FieldStore;
    owner: string;
    onChange: (ref?: EvidenceRef) => void;
}) {
    const [file, setFile] = useState<Blob>();
    const [location, setLocation] = useState<GeolocationPosition>();
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [preview, setPreview] = useState("");
    useEffect(() => {
        if (!file) return;
        const url = URL.createObjectURL(file);
        setPreview(url);
        return () => URL.revokeObjectURL(url);
    }, [file]);
    const locate = () => {
        onChange(undefined);
        setError("");
        setBusy(true);
        if (!navigator.geolocation) {
            setError("Lokasi tidak tersedia pada perangkat ini.");
            setBusy(false);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (p) => {
                setLocation(p);
                setBusy(false);
            },
            (e) => {
                setLocation(undefined);
                setError(
                    e.code === 1
                        ? "Izin lokasi ditolak. Bukti belum lengkap."
                        : "Lokasi belum diperoleh. Coba lagi di tempat aman.",
                );
                setBusy(false);
            },
            { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 },
        );
    };
    const save = async () => {
        if (!file || !location) return;
        if (Date.now() - location.timestamp > 60000) {
            setError("Lokasi sudah kedaluwarsa. Ambil lokasi baru.");
            onChange(undefined);
            return;
        }
        const id = crypto.randomUUID();
        const capturedAt = new Date().toISOString();
        try {
            await store.saveEvidence({
                key: `${owner}:${id}`,
                owner,
                blob: file,
                capturedAt,
                ...location.coords,
                latitude: location.coords.latitude,
                longitude: location.coords.longitude,
                accuracy: location.coords.accuracy,
                mapStatus: "pending",
            });
            onChange({
                id,
                latitude: location.coords.latitude,
                longitude: location.coords.longitude,
                accuracy: location.coords.accuracy,
                capturedAt,
            });
            setError(
                "Foto tersimpan lokal. Snapshot peta masih menunggu integrasi.",
            );
        } catch {
            setError("Foto gagal disimpan. Periksa ruang penyimpanan.");
            onChange(undefined);
        }
    };
    return (
        <div class="evidence">
            <strong>Bukti foto & lokasi</strong>
            <p class="muted">
                Capture browser belum membuktikan kamera asli atau bebas mock
                GPS.
            </p>
            <label class="upload">
                <Icon name="camera" /> Ambil foto
                <input
                    aria-label="Foto bukti"
                    type="file"
                    accept="image/jpeg,image/png,image/webp"
                    capture="environment"
                    onChange={async (e) => {
                        onChange(undefined);
                        setError("");
                        const f = e.currentTarget.files?.[0];
                        if (!f) return;
                        try {
                            setFile(await compress(f));
                        } catch (x) {
                            setFile(undefined);
                            setError(String(x));
                        }
                    }}
                />
            </label>
            {preview && (
                <img
                    class="photo-preview"
                    src={preview}
                    alt="Pratinjau foto bukti lokal"
                />
            )}
            <button
                class="secondary"
                type="button"
                onClick={locate}
                disabled={busy}
            >
                <Icon name="pin" size={18} />
                {busy ? "Mencari lokasi…" : "Ambil lokasi sekarang"}
            </button>
            {location && (
                <p class="coordinates">
                    {location.coords.latitude.toFixed(6)},{" "}
                    {location.coords.longitude.toFixed(6)} · ±
                    {Math.round(location.coords.accuracy)} m
                </p>
            )}
            <button
                type="button"
                class="secondary"
                disabled={!file || !location || busy}
                onClick={() => void save()}
            >
                Simpan bukti lokal
            </button>
            {error && (
                <p role="status" class="notice">
                    {error}
                </p>
            )}
            <small>
                Map pending · bukti ini belum memenuhi gate foto berpeta resmi.
            </small>
        </div>
    );
}

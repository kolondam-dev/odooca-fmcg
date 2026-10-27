import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
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
const referenceKey = (owner: string, ref?: EvidenceRef) =>
    JSON.stringify([
        owner,
        ref?.id,
        ref?.latitude,
        ref?.longitude,
        ref?.accuracy,
        ref?.capturedAt,
    ]);
export function EvidenceCapture({
    store,
    owner,
    onChange,
    existingRef,
}: {
    store: FieldStore;
    owner: string;
    onChange: (ref?: EvidenceRef) => void;
    existingRef?: EvidenceRef;
}) {
    const [file, setFile] = useState<Blob>();
    const [location, setLocation] = useState<GeolocationPosition>();
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [preview, setPreview] = useState("");
    const generation = useRef(0);
    const selfChange = useRef<string | undefined>(undefined);
    function report(ref?: EvidenceRef) {
        selfChange.current = referenceKey(owner, ref);
        onChange(ref);
    }
    const scope = referenceKey(owner, existingRef);
    useLayoutEffect(() => {
        if (selfChange.current === scope) {
            selfChange.current = undefined;
            return;
        }
        selfChange.current = undefined;
        const ticket = ++generation.current;
        setFile(undefined);
        setLocation(undefined);
        setPreview("");
        setError("");
        setBusy(false);
        if (!existingRef) return;
        void store
            .listEvidence(owner)
            .then((rows) => {
                const found = rows.find(
                    (e) =>
                        e.owner === owner &&
                        e.key === `${owner}:${existingRef.id}` &&
                        e.capturedAt === existingRef.capturedAt &&
                        e.latitude === existingRef.latitude &&
                        e.longitude === existingRef.longitude &&
                        e.accuracy === existingRef.accuracy,
                );
                if (!found || !(found.blob instanceof Blob) || !found.blob.size)
                    throw new Error("missing");
                if (generation.current === ticket) setFile(found.blob);
            })
            .catch(() => {
                if (generation.current === ticket)
                    setError(
                        "Foto lokal tidak dapat dipulihkan. Metadata saja bukan bukti lengkap.",
                    );
            });
    }, [scope, store]);
    useEffect(
        () => () => {
            generation.current++;
        },
        [],
    );
    useEffect(() => {
        if (!file) {
            setPreview("");
            return;
        }
        const url = URL.createObjectURL(file);
        setPreview(url);
        return () => URL.revokeObjectURL(url);
    }, [file]);
    async function selectFile(f?: File) {
        const ticket = ++generation.current;
        report(undefined);
        setFile(undefined);
        setLocation(undefined);
        setPreview("");
        setError("");
        setBusy(!!f);
        if (!f) return;
        try {
            const blob = await compress(f);
            if (generation.current === ticket) setFile(blob);
        } catch (e) {
            if (generation.current === ticket)
                setError(e instanceof Error ? e.message : "Foto tidak valid.");
        } finally {
            if (generation.current === ticket) setBusy(false);
        }
    }
    function locate() {
        const ticket = ++generation.current;
        report(undefined);
        setLocation(undefined);
        setError("");
        setBusy(true);
        if (!navigator.geolocation) {
            setError("Lokasi tidak tersedia pada perangkat ini.");
            setBusy(false);
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (p) => {
                if (generation.current === ticket) {
                    setLocation(p);
                    setBusy(false);
                }
            },
            (e) => {
                if (generation.current === ticket) {
                    setError(
                        e.code === 1
                            ? "Izin lokasi ditolak. Bukti belum lengkap."
                            : "Lokasi belum diperoleh. Coba lagi di tempat aman.",
                    );
                    setBusy(false);
                }
            },
            { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 },
        );
    }
    async function save() {
        if (!file || !location || busy) return;
        if (Date.now() - location.timestamp > 60000) {
            setError("Lokasi sudah kedaluwarsa. Ambil lokasi baru.");
            report(undefined);
            return;
        }
        const ticket = ++generation.current;
        setBusy(true);
        const id = crypto.randomUUID(),
            capturedAt = new Date().toISOString();
        try {
            await store.saveEvidence({
                key: `${owner}:${id}`,
                owner,
                blob: file,
                capturedAt,
                latitude: location.coords.latitude,
                longitude: location.coords.longitude,
                accuracy: location.coords.accuracy,
                mapStatus: "pending",
            });
            if (generation.current === ticket) {
                report({
                    id,
                    latitude: location.coords.latitude,
                    longitude: location.coords.longitude,
                    accuracy: location.coords.accuracy,
                    capturedAt,
                });
                setError(
                    "Foto tersimpan lokal. Snapshot peta masih menunggu integrasi.",
                );
            }
        } catch {
            if (generation.current === ticket) {
                setError("Foto gagal disimpan. Periksa ruang penyimpanan.");
                report(undefined);
            }
        } finally {
            if (generation.current === ticket) setBusy(false);
        }
    }
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
                    onChange={(e) =>
                        void selectFile(e.currentTarget.files?.[0])
                    }
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
                {busy ? "Memproses bukti…" : "Ambil lokasi sekarang"}
            </button>
            {!location && existingRef && (
                <p class="coordinates">
                    Lokasi bukti tersimpan: {existingRef.latitude.toFixed(6)},{" "}
                    {existingRef.longitude.toFixed(6)} · ±
                    {Math.round(existingRef.accuracy)} m ·{" "}
                    {new Date(existingRef.capturedAt).toLocaleString("id-ID", {
                        timeZone: "Asia/Makassar",
                    })}{" "}
                    WITA
                </p>
            )}
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

import { useEffect, useRef, useState } from "preact/hooks";
import { uploadOfficialEvidence } from "../data/official-evidence";
import { ApiError, type Identity, type Snapshot } from "../domain/contracts";
import type {
    OfficialEvidenceMetadata,
    OfficialEvidenceReceipt,
} from "../domain/official-evidence";

type Fix = {
    latitude: number;
    longitude: number;
    accuracy: number;
    sampled: string;
};
export function OfficialEvidence({
    identity,
    snapshot,
    expired,
}: {
    identity: Identity;
    snapshot: Snapshot;
    expired: () => void;
}) {
    const [outlet, setOutlet] = useState(snapshot.outlets[0]?.id ?? "");
    const [photo, setPhoto] = useState<File>();
    const [selected, setSelected] = useState("");
    const [fix, setFix] = useState<Fix>();
    const [receipt, setReceipt] = useState<OfficialEvidenceReceipt>();
    const [image, setImage] = useState("");
    const [busy, setBusy] = useState(false);
    const [message, setMessage] = useState("");
    const sourceInput = useRef<HTMLInputElement>(null);
    const generation = useRef(0),
        pending = useRef<OfficialEvidenceMetadata | undefined>(undefined),
        controller = useRef<AbortController | undefined>(undefined);
    useEffect(
        () => () => {
            generation.current++;
            controller.current?.abort();
        },
        [],
    );
    useEffect(
        () => () => {
            if (image) URL.revokeObjectURL(image);
        },
        [image],
    );
    function reset() {
        pending.current = undefined;
        setReceipt(undefined);
        setImage("");
        setMessage("");
    }
    function locate() {
        const ticket = ++generation.current;
        reset();
        setFix(undefined);
        setBusy(true);
        if (!navigator.geolocation) {
            setBusy(false);
            setMessage("Geolocation tidak tersedia.");
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (position) => {
                if (generation.current !== ticket) return;
                setFix({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy,
                    sampled: new Date(position.timestamp).toISOString(),
                });
                setBusy(false);
            },
            () => {
                if (generation.current === ticket) {
                    setBusy(false);
                    setMessage(
                        "Lokasi tidak diperoleh. Aktifkan izin lokasi dan coba kembali.",
                    );
                }
            },
            { enableHighAccuracy: true, maximumAge: 0, timeout: 12000 },
        );
    }
    async function upload() {
        if (!photo || !fix || !outlet || busy) return;
        const ticket = ++generation.current;
        setBusy(true);
        setMessage("");
        controller.current = new AbortController();
        const timer = window.setTimeout(
            () => controller.current?.abort(),
            30000,
        );
        try {
            const metadata = pending.current ?? {
                client_uuid: crypto.randomUUID(),
                outlet_id: outlet,
                business_date: identity.businessDate,
                snapshot_version: snapshot.version,
                photo_selected_at: selected,
                device_recorded_at: new Date().toISOString(),
                fix_sampled_at: fix.sampled,
                latitude: fix.latitude,
                longitude: fix.longitude,
                accuracy: fix.accuracy,
            };
            pending.current = metadata;
            const result = await uploadOfficialEvidence(
                metadata,
                photo,
                identity.csrfToken ?? "",
                controller.current.signal,
            );
            if (generation.current !== ticket) return;
            setReceipt(result.receipt);
            setImage(URL.createObjectURL(result.watermarked));
            setMessage("Bukti tersimpan di server.");
        } catch (error) {
            if (generation.current !== ticket) return;
            if (
                error instanceof ApiError &&
                [400, 401, 403, 404, 409].includes(error.status)
            ) {
                expired();
                return;
            }
            setMessage(
                error instanceof ApiError
                    ? error.message
                    : "Unggah belum terkonfirmasi. Coba ulang dengan UUID yang sama.",
            );
        } finally {
            clearTimeout(timer);
            if (generation.current === ticket) setBusy(false);
        }
    }
    return (
        <section class="read-card" aria-label="Bukti foto resmi">
            <h2>Bukti foto resmi · staging</h2>
            <p>
                Server memvalidasi geofence dari master outlet. Unggahan ini
                menyimpan bukti; belum menjadi check-in atau POD.
            </p>
            <label>
                Outlet bukti
                <select
                    disabled={busy || !!receipt}
                    value={outlet}
                    onChange={(event) => {
                        reset();
                        setFix(undefined);
                        setOutlet(event.currentTarget.value);
                    }}
                >
                    {snapshot.outlets.map((row) => (
                        <option key={row.id} value={row.id}>
                            {row.name}
                        </option>
                    ))}
                </select>
            </label>
            <label>
                Foto sumber JPEG/PNG
                <input
                    ref={sourceInput}
                    type="file"
                    accept="image/jpeg,image/png"
                    capture="environment"
                    disabled={busy || !!receipt}
                    onChange={(event) => {
                        reset();
                        setPhoto(event.currentTarget.files?.[0]);
                        setSelected(new Date().toISOString());
                    }}
                />
            </label>
            <div class="read-actions">
                <button disabled={busy || !!receipt} onClick={locate}>
                    Ambil GPS bukti
                </button>
                <button
                    disabled={busy || !photo || !fix || !outlet || !!receipt}
                    onClick={() => void upload()}
                >
                    Unggah bukti ke server
                </button>
            </div>
            {fix && (
                <p>
                    GPS {fix.latitude.toFixed(6)}, {fix.longitude.toFixed(6)} ·
                    ±{fix.accuracy.toFixed(1)} m
                </p>
            )}
            <p role="status">{busy ? "Memproses bukti…" : message}</p>
            {receipt && (
                <button
                    disabled={busy}
                    onClick={() => {
                        generation.current++;
                        reset();
                        setPhoto(undefined);
                        setFix(undefined);
                        setSelected("");
                        if (sourceInput.current) sourceInput.current.value = "";
                    }}
                >
                    Buat bukti baru
                </button>
            )}
            {receipt && (
                <>
                    <p>Waktu perangkat: {receipt.device_recorded_at}</p>
                    <p>Diterima server: {receipt.received_at}</p>
                    <p>
                        Jarak tervalidasi {receipt.distance_m.toFixed(1)} m /
                        radius {receipt.radius_m} m
                    </p>
                    <p>UUID bukti: {receipt.client_uuid}</p>
                    <img
                        src={image}
                        alt="Foto watermark dari server"
                        style={{ maxWidth: "100%", height: "auto" }}
                    />
                </>
            )}
            <p>
                Waktu pencatatan berbeda dari waktu shutter asli. GPS dan
                keaslian foto belum dapat dijamin. Retry memakai UUID yang sama;
                tab/reload tidak menyimpan draft unggahan.
            </p>
        </section>
    );
}

import { useEffect, useRef, useState } from "preact/hooks";
import { CameraViewfinder, type CameraCaptureResult } from "./CameraViewfinder";
import { CheckinMap } from "./CheckinMap";
import { Icon } from "./Icon";
import type { MapFix, MapSite } from "../domain/checkin-map";
import type { EvidenceRef } from "./Evidence";
import { renderEvidencePackage } from "../domain/evidence-render";
import type { FieldStore } from "../storage/store";
export function AttendanceCapture({
    store,
    owner,
    onChange,
    employeeName,
    companyName,
    mapSite,
}: {
    store: FieldStore;
    owner: string;
    onChange: (ref?: EvidenceRef) => void;
    employeeName: string;
    companyName: string;
    mapSite?: MapSite;
}) {
    const [fix, setFix] = useState<MapFix & { timestamp: number }>();
    const [address, setAddress] = useState("");
    const [photo, setPhoto] = useState<Blob>();
    const [preview, setPreview] = useState("");
    const [camera, setCamera] = useState(false);
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");
    const [captured, setCaptured] = useState("");
    const resultView = useRef<HTMLDivElement>(null);
    const generation = useRef(0);
    const changed = useRef(onChange);
    changed.current = onChange;
    function locate(precise: boolean) {
        const ticket = ++generation.current;
        changed.current(undefined);
        setPhoto(undefined);
        setCaptured("");
        setBusy(true);
        setError("");
        if (!navigator.geolocation) {
            setBusy(false);
            setError("Lokasi tidak didukung perangkat ini.");
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (position) => {
                if (ticket !== generation.current) return;
                setFix({
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                    accuracy: position.coords.accuracy,
                    timestamp: position.timestamp,
                });
                setBusy(false);
            },
            (failure) => {
                if (ticket !== generation.current) return;
                setBusy(false);
                setFix(undefined);
                setError(
                    failure.code === 1
                        ? "Izin lokasi ditolak. Aktifkan izin lokasi di browser."
                        : "Lokasi belum diperoleh. Coba kembali.",
                );
            },
            {
                enableHighAccuracy: precise,
                maximumAge: precise ? 0 : 30000,
                timeout: 12000,
            },
        );
    }
    useEffect(() => {
        locate(false);
        return () => {
            generation.current++;
        };
    }, []);
    useEffect(() => {
        if (!photo) {
            setPreview("");
            return;
        }
        const url = URL.createObjectURL(photo);
        setPreview(url);
        return () => URL.revokeObjectURL(url);
    }, [photo]);
    useEffect(() => {
        if (!preview) return;
        const frame = requestAnimationFrame(() =>
            resultView.current?.scrollIntoView({
                block: "start",
                behavior: "instant",
            }),
        );
        return () => cancelAnimationFrame(frame);
    }, [preview]);
    async function capture(result: CameraCaptureResult) {
        setCamera(false);
        if (!fix) return;
        const ticket = ++generation.current;
        setBusy(true);
        setError("");
        changed.current(undefined);
        try {
            if (Date.now() - fix.timestamp > 60000)
                throw new Error(
                    "Lokasi kedaluwarsa. Ambil lokasi presisi, lalu foto ulang.",
                );
            const at = new Date(result.timestamp).toISOString();
            const ref = {
                id: crypto.randomUUID(),
                latitude: fix.latitude,
                longitude: fix.longitude,
                accuracy: fix.accuracy,
                capturedAt: at,
            };
            const row = await renderEvidencePackage(
                result.blob,
                owner,
                ref,
                at,
                new Date(fix.timestamp).toISOString(),
                __DEMO__,
                {
                    company: companyName,
                    employee: employeeName,
                    address: address.trim(),
                },
            );
            if (ticket !== generation.current) return;
            await store.saveEvidence(row);
            if (ticket !== generation.current) return;
            setPhoto(row.blob);
            setCaptured(at);
            changed.current({ ...ref, packageHash: row.visual!.bindingSha256 });
        } catch (failure) {
            if (ticket === generation.current)
                setError(
                    failure instanceof Error
                        ? failure.message
                        : "Foto gagal disimpan. Coba kembali.",
                );
        } finally {
            if (ticket === generation.current) setBusy(false);
        }
    }
    return (
        <section
            class="attendance-capture"
            aria-label="Lokasi dan foto absensi"
            aria-busy={busy}
        >
            {preview && (
                <div class="attendance-result" ref={resultView}>
                    <img
                        src={preview}
                        class="photo-preview"
                        alt="Foto absensi dengan watermark"
                    />
                    <p>
                        {companyName} · {employeeName}
                    </p>
                    <p>
                        {new Date(captured).toLocaleString("id-ID", {
                            timeZone: "Asia/Makassar",
                        })}{" "}
                        WITA
                    </p>
                    <p>{address}</p>
                    <small>
                        Tersimpan di perangkat · belum diverifikasi server
                    </small>
                </div>
            )}
            {mapSite ? (
                <CheckinMap compact site={mapSite} fix={fix} />
            ) : (
                <p class="notice">
                    Master lokasi kantor belum tersedia. Hubungi admin.
                </p>
            )}
            {fix && (
                <p class="coordinates">
                    {fix.latitude.toFixed(6)}, {fix.longitude.toFixed(6)} · ±
                    {Math.round(fix.accuracy)} m
                </p>
            )}
            <label>
                Alamat / nama lokasi
                <input
                    value={address}
                    maxLength={140}
                    required
                    placeholder="Alamat lengkap lokasi Anda saat ini"
                    disabled={busy || camera}
                    onInput={(event) => {
                        generation.current++;
                        setAddress(event.currentTarget.value);
                        setPhoto(undefined);
                        setCaptured("");
                        changed.current(undefined);
                    }}
                />
            </label>
            <div class="capture-actions">
                <button
                    type="button"
                    class="secondary"
                    disabled={busy}
                    onClick={() => locate(true)}
                >
                    <Icon name="pin" size={18} />
                    Ambil Lokasi Presisi
                </button>
                <button
                    type="button"
                    disabled={busy || !fix || !address.trim() || !mapSite}
                    onClick={() => setCamera(true)}
                >
                    <Icon name="camera" size={18} />
                    {photo ? "Foto ulang" : "Buka Kamera"}
                </button>
            </div>
            {busy && <p role="status">Menyiapkan bukti…</p>}
            {error && (
                <p class="form-error" role="alert">
                    {error}
                </p>
            )}
            {camera && (
                <CameraViewfinder
                    rawCapture
                    title="Foto absensi"
                    salespersonName={employeeName}
                    outletName={mapSite?.name}
                    onCapture={(result) => void capture(result)}
                    onClose={() => setCamera(false)}
                />
            )}
        </section>
    );
}

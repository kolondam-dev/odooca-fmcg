import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { FieldStore } from "../storage/store";
import { Icon } from "./Icon";
import { CheckinMap } from "./CheckinMap";
import type { MapSite } from "../domain/checkin-map";
import { CameraViewfinder, type CameraCaptureResult } from "./CameraViewfinder";
import {
    assertLocalEvidence,
    type EvidenceReference,
} from "../domain/evidence-package";
import {
    compressEvidence,
    renderEvidencePackage,
} from "../domain/evidence-render";
export type EvidenceRef = EvidenceReference;
const referenceKey = (owner: string, ref?: EvidenceRef) =>
    JSON.stringify([
        owner,
        ref?.id,
        ref?.latitude,
        ref?.longitude,
        ref?.accuracy,
        ref?.capturedAt,
        ref?.packageHash,
    ]);
export function EvidenceCapture({
    store,
    owner,
    onChange,
    existingRef,
    readOnly = false,
    mapSite,
}: {
    store: FieldStore;
    owner: string;
    onChange: (ref?: EvidenceRef) => void;
    existingRef?: EvidenceRef;
    readOnly?: boolean;
    mapSite?: MapSite;
}) {
    const [file, setFile] = useState<Blob>();
    const [display, setDisplay] = useState<Blob>();
    const [map, setMap] = useState<Blob>();
    const [mapPreview, setMapPreview] = useState("");
    const [selectedAt, setSelectedAt] = useState<string>();
    const [location, setLocation] = useState<GeolocationPosition>();
    const [simulated, setSimulated] = useState(false);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    const [preview, setPreview] = useState("");
    const [showCamera, setShowCamera] = useState(false);

    async function onCameraCapture(res: CameraCaptureResult) {
        const ticket = ++generation.current;
        report(undefined);
        setFile(res.blob);
        setDisplay(res.blob);
        setSelectedAt(new Date(res.timestamp).toISOString());
        setLocation({
            coords: {
                latitude: res.latitude,
                longitude: res.longitude,
                accuracy: res.accuracy,
                altitude: null,
                altitudeAccuracy: null,
                heading: null,
                speed: null,
            },
            timestamp: res.timestamp,
        } as GeolocationPosition);
        setError("");
        setBusy(true);

        const id = crypto.randomUUID();
        const capturedAt = new Date().toISOString();
        try {
            const ref = {
                id,
                latitude: res.latitude,
                longitude: res.longitude,
                accuracy: res.accuracy,
                capturedAt,
            };
            const packaged = await renderEvidencePackage(
                res.blob,
                owner,
                ref,
                new Date(res.timestamp).toISOString(),
                new Date(res.timestamp).toISOString(),
                true,
            );
            if (generation.current === ticket) {
                await store.saveEvidence(packaged);
                setMap(packaged.visual?.map);
                setDisplay(packaged.blob);
                report(ref);
            }
        } catch (e) {
            if (generation.current === ticket) {
                setError(
                    e instanceof Error ? e.message : "Gagal menyimpan bukti.",
                );
                report(undefined);
            }
        } finally {
            if (generation.current === ticket) setBusy(false);
        }
    }
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
        setDisplay(undefined);
        setMap(undefined);
        setSelectedAt(undefined);
        setLocation(undefined);
        setPreview("");
        setError("");
        setBusy(false);
        if (!existingRef) return;
        void store
            .listEvidence(owner)
            .then(async (rows) => {
                const found = rows.find(
                    (e) =>
                        e.owner === owner &&
                        e.key === `${owner}:${existingRef.id}` &&
                        e.capturedAt === existingRef.capturedAt &&
                        e.latitude === existingRef.latitude &&
                        e.longitude === existingRef.longitude &&
                        e.accuracy === existingRef.accuracy,
                );
                await assertLocalEvidence(found, existingRef, owner);
                if (generation.current === ticket) {
                    setDisplay(found!.blob);
                    setMap(found!.visual?.map);
                }
            })
            .catch(() => {
                if (generation.current === ticket)
                    setError(
                        "Foto lokal tidak dapat dipulihkan. Metadata saja bukan bukti lengkap.",
                    );
            });
    }, [scope, store]);
    useLayoutEffect(
        () => () => {
            generation.current++;
        },
        [],
    );
    useEffect(() => {
        if (!display) {
            setPreview("");
            return;
        }
        const url = URL.createObjectURL(display);
        setPreview(url);
        return () => URL.revokeObjectURL(url);
    }, [display]);
    useEffect(() => {
        if (!map) {
            setMapPreview("");
            return;
        }
        const url = URL.createObjectURL(map);
        setMapPreview(url);
        return () => URL.revokeObjectURL(url);
    }, [map]);
    async function selectFile(f?: File) {
        const ticket = ++generation.current;
        report(undefined);
        setFile(undefined);
        setDisplay(undefined);
        setMap(undefined);
        setSelectedAt(undefined);
        setLocation(undefined);
        setPreview("");
        setError("");
        setBusy(!!f);
        if (!f) return;
        try {
            const at = new Date().toISOString();
            const blob = await compressEvidence(f);
            if (generation.current === ticket) {
                setFile(blob);
                setDisplay(blob);
                setSelectedAt(at);
            }
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
        setSimulated(false);
        setMap(undefined);
        setDisplay(file);
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
        if (!file || !location || !selectedAt || busy) return;
        if (!__DEMO__ && Date.now() - location.timestamp > 60000) {
            setError("Lokasi sudah kedaluwarsa. Ambil lokasi baru.");
            report(undefined);
            return;
        }
        const ticket = ++generation.current;
        setBusy(true);
        const id = crypto.randomUUID(),
            capturedAt = new Date().toISOString();
        try {
            const ref = {
                id,
                latitude: location.coords.latitude,
                longitude: location.coords.longitude,
                accuracy: location.coords.accuracy,
                capturedAt,
            };
            if (!Number.isFinite(location.timestamp))
                throw new Error("Waktu lokasi tidak valid. Ambil lokasi baru.");
            const row = await renderEvidencePackage(
                file,
                owner,
                ref,
                selectedAt,
                new Date(location.timestamp).toISOString(),
                __DEMO__,
            );
            if (generation.current !== ticket) return;
            await store.saveEvidence(row);
            if (generation.current === ticket) {
                setDisplay(row.blob);
                setMap(row.visual!.map);
                report({ ...ref, packageHash: row.visual!.bindingSha256 });
                setError(
                    "Foto dan pinpoint simulasi tersimpan lokal. Peta resmi belum tersedia.",
                );
            }
        } catch (error) {
            if (generation.current === ticket) {
                setError(
                    error instanceof Error
                        ? error.message
                        : "Foto gagal disimpan. Periksa ruang penyimpanan.",
                );
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
            {!readOnly && __DEMO__ && (
                <button
                    class="secondary"
                    disabled={busy}
                    onClick={() => {
                        ++generation.current;
                        report(undefined);
                        setMap(undefined);
                        setDisplay(file);
                        setSimulated(true);
                        setLocation({
                            coords: {
                                latitude: 1.465,
                                longitude: 124.833,
                                accuracy: 1,
                                altitude: null,
                                altitudeAccuracy: null,
                                heading: null,
                                speed: null,
                            },
                            timestamp: Date.now(),
                        } as GeolocationPosition);
                        setError(
                            "Lokasi DEMO dipilih; bukan lokasi terverifikasi.",
                        );
                    }}
                >
                    Gunakan lokasi demo
                </button>
            )}
            {!readOnly && (
                <>
                    <button
                        type="button"
                        class="camera-open-btn"
                        onClick={() => setShowCamera(true)}
                        disabled={busy}
                    >
                        <Icon name="camera" size={20} />
                        <span>Buka Kamera Bukti</span>
                    </button>
                    <input
                        aria-label="Foto bukti"
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        capture="environment"
                        style={{ display: "none" }}
                        onChange={(e) =>
                            void selectFile(e.currentTarget.files?.[0])
                        }
                    />
                    {showCamera && (
                        <CameraViewfinder
                            title="Ambil Foto Bukti Lapangan"
                            outletName={mapSite?.name}
                            defaultCoordinates={
                                mapSite
                                    ? {
                                          latitude: mapSite.latitude,
                                          longitude: mapSite.longitude,
                                      }
                                    : undefined
                            }
                            onCapture={(res) => {
                                setShowCamera(false);
                                void onCameraCapture(res);
                            }}
                            onClose={() => setShowCamera(false)}
                        />
                    )}
                </>
            )}
            {preview && (
                <img
                    class="photo-preview"
                    src={preview}
                    alt="Pratinjau foto bukti lokal"
                />
            )}
            {mapPreview && (
                <figure class="evidence-map">
                    <img
                        src={mapPreview}
                        alt="Pinpoint simulasi tanpa basemap"
                    />
                    <figcaption>
                        Grid koordinat simulasi · bukan peta jalan. Area biru
                        menunjukkan akurasi lokasi.
                    </figcaption>
                </figure>
            )}
            {!readOnly && (
                <button
                    class="secondary"
                    type="button"
                    onClick={locate}
                    disabled={busy}
                >
                    <Icon name="pin" size={18} />
                    {busy ? "Memproses bukti…" : "Ambil lokasi sekarang"}
                </button>
            )}
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
            {mapSite && (
                <CheckinMap
                    site={mapSite}
                    fix={
                        location
                            ? {
                                  latitude: location.coords.latitude,
                                  longitude: location.coords.longitude,
                                  accuracy: location.coords.accuracy,
                                  simulated,
                              }
                            : existingRef
                              ? {
                                    latitude: existingRef.latitude,
                                    longitude: existingRef.longitude,
                                    accuracy: existingRef.accuracy,
                                    simulated: __DEMO__,
                                }
                              : undefined
                    }
                />
            )}
            {!readOnly && (
                <button
                    type="button"
                    class="secondary"
                    disabled={!file || !location || !selectedAt || busy}
                    onClick={() => void save()}
                >
                    Simpan bukti lokal
                </button>
            )}
            {error && (
                <p role="status" class="notice">
                    {error}
                </p>
            )}
            {existingRef && !existingRef.packageHash && (
                <small>
                    Bukti lama belum memiliki paket watermark/hash/pinpoint.
                    Pilih foto baru untuk membuat paket baru.
                </small>
            )}
            <small>
                Map pending · foto baru memiliki watermark waktu pencatatan dan
                koordinat. Pinpoint simulasi tidak memenuhi gate peta resmi.
            </small>
        </div>
    );
}

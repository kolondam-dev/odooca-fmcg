import { useContext } from "preact/hooks";
import { EvidenceIdentityContext } from "../ui/evidenceIdentity";
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { FieldStore } from "../storage/store";
import { isDemoMode } from "../domain/running-mode";
import { Icon } from "./Icon";
import { Button, Callout } from "../ui";
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
    fence: fenceProp,
}: {
    store: FieldStore;
    owner: string;
    onChange: (ref?: EvidenceRef) => void;
    existingRef?: EvidenceRef;
    readOnly?: boolean;
    mapSite?: MapSite;
    /** Geofence tanpa peta: foto di luar radius ditolak kamera. */
    fence?: { latitude: number; longitude: number; radius: number };
}) {
    const identity = useContext(EvidenceIdentityContext);
    const caption = identity
        ? {
              ...identity,
              address: mapSite
                  ? `Tujuan: ${mapSite.name}`
                  : "Lokasi perangkat (lihat koordinat)",
          }
        : undefined;
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
    const fileInputRef = useRef<HTMLInputElement>(null);

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
            timestamp: res.fixTimestamp,
        } as GeolocationPosition);
        setError("");
        setBusy(true);

        const id = crypto.randomUUID();
        const capturedAt = new Date().toISOString();
        try {
            if (!__DEMO__ && !isDemoMode() && res.simulated)
                throw new Error(
                    "Lokasi perangkat belum tersedia. Ambil ulang foto setelah GPS siap.",
                );
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
                new Date(res.fixTimestamp).toISOString(),
                __DEMO__ || isDemoMode(),
                caption,
            );
            if (generation.current === ticket) {
                await store.saveEvidence(packaged);
                if (generation.current !== ticket) return;
                setMap(packaged.visual?.map);
                setDisplay(packaged.blob);
                report({ ...ref, packageHash: packaged.visual!.bindingSha256 });
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
                    if (isDemoMode()) {
                        setLocation({
                            coords: {
                                latitude: mapSite?.latitude ?? 1.48,
                                longitude: mapSite?.longitude ?? 124.84,
                                accuracy: 15,
                                altitude: null,
                                altitudeAccuracy: null,
                                heading: null,
                                speed: null,
                            },
                            timestamp: Date.now(),
                        } as GeolocationPosition);
                        setBusy(false);
                        return;
                    }
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
        if (
            !__DEMO__ &&
            !isDemoMode() &&
            Date.now() - location.timestamp > 60000
        ) {
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
                __DEMO__ || isDemoMode(),
                caption,
            );
            if (generation.current !== ticket) return;
            await store.saveEvidence(row);
            if (generation.current === ticket) {
                setDisplay(row.blob);
                setMap(row.visual!.map);
                report({ ...ref, packageHash: row.visual!.bindingSha256 });
                setError("Foto dan lokasi tersimpan.");
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
    const fix = location
        ? `${location.coords.latitude.toFixed(6)}, ${location.coords.longitude.toFixed(6)} · ±${Math.round(location.coords.accuracy)} m`
        : existingRef
          ? `${existingRef.latitude.toFixed(6)}, ${existingRef.longitude.toFixed(6)} · ±${Math.round(existingRef.accuracy)} m · ${new Date(
                existingRef.capturedAt,
            ).toLocaleString("id-ID", {
                timeZone: "Asia/Makassar",
            })} WITA`
          : "";
    return (
        <div class="ev">
            <p class="ev__title">Bukti foto & lokasi</p>
            {!readOnly && __QA_TOOLS__ && (
                <Button
                    variant="sec"
                    size="sm"
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
                            "Lokasi acuan dipakai; bukan lokasi terverifikasi.",
                        );
                    }}
                >
                    Gunakan lokasi acuan
                </Button>
            )}
            {!readOnly && (
                <>
                    <button
                        type="button"
                        class="ev__slot"
                        onClick={() => setShowCamera(true)}
                        disabled={busy}
                    >
                        <Icon name="camera" size={24} />
                        <span>Buka Kamera Bukti</span>
                    </button>
                    <button
                        type="button"
                        class="ev__file"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={busy}
                    >
                        <Icon name="receipt" size={18} />
                        <span>Pilih Foto dari Galeri / Berkas</span>
                    </button>
                    <input
                        ref={fileInputRef}
                        aria-label="Foto bukti dari berkas"
                        type="file"
                        accept="image/jpeg,image/png,image/webp"
                        style={{ display: "none" }}
                        onChange={(e) =>
                            void selectFile(e.currentTarget.files?.[0])
                        }
                    />
                    {showCamera && (
                        <CameraViewfinder
                            title="Foto bukti"
                            salespersonName={identity?.employee}
                            rawCapture
                            outletName={mapSite?.name}
                            fence={
                                fenceProp ??
                                (mapSite && !mapSite.simulated
                                    ? {
                                          latitude: mapSite.latitude,
                                          longitude: mapSite.longitude,
                                          radius: mapSite.radius,
                                      }
                                    : undefined)
                            }
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
                    class="ev__photo"
                    src={preview}
                    alt="Pratinjau foto bukti lokal"
                />
            )}
            {mapPreview && (
                <figure class="ev__map">
                    <img src={mapPreview} alt="Pinpoint tanpa basemap" />
                    <figcaption>
                        Grid koordinat · bukan peta jalan. Area biru menunjukkan
                        akurasi lokasi.
                    </figcaption>
                </figure>
            )}
            {!readOnly && !existingRef && file && (
                <Button
                    variant="sec"
                    size="md"
                    icon="pin"
                    onClick={locate}
                    disabled={busy}
                >
                    {busy ? "Memproses bukti…" : "Ambil lokasi sekarang"}
                </Button>
            )}
            {fix && <p class="ev__fix">{fix}</p>}
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
            {!readOnly && !existingRef && file && (
                <Button
                    variant="pri"
                    size="md"
                    icon="check"
                    disabled={!file || !location || !selectedAt || busy}
                    onClick={() => void save()}
                >
                    Simpan bukti lokal
                </Button>
            )}
            {error && (
                <div role="status">
                    <Callout tone="warn">{error}</Callout>
                </div>
            )}
            {existingRef && !existingRef.packageHash && (
                <p class="ev__note">
                    Bukti lama belum memiliki paket watermark/hash/pinpoint.
                    Pilih foto baru untuk membuat paket baru.
                </p>
            )}
            <p class="ev__note">Bukti lokal · belum divalidasi server.</p>
        </div>
    );
}

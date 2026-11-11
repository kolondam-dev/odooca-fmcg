import { useDialog } from "../ui/useDialog";
import { useBackLayer } from "../ui/navigation";
import { useEffect, useRef, useState } from "preact/hooks";
import { Icon } from "./Icon";
import { distanceMeters } from "../domain/format";

export interface CameraCaptureResult {
    blob: Blob;
    timestamp: number;
    fixTimestamp: number;
    latitude: number;
    longitude: number;
    accuracy: number;
    simulated?: boolean;
}

interface CameraViewfinderProps {
    title?: string;
    outletName?: string;
    salespersonName?: string;
    defaultCoordinates?: { latitude: number; longitude: number };
    rawCapture?: boolean;
    /** Area yang diizinkan: di luar radius, shutter dikunci (DS: Kamera_luar). */
    fence?: { latitude: number; longitude: number; radius: number };
    onCapture: (result: CameraCaptureResult) => void;
    onClose: () => void;
}

export const MAX_CANVAS_DIM = 1280;
export const BANNER_HEIGHT = 110;

export function computeWatermarkedDimensions(
    sourceWidth: number,
    sourceHeight: number,
    rawCapture = false,
): {
    targetWidth: number;
    targetHeight: number;
    bannerHeight: number;
    totalWidth: number;
    totalHeight: number;
} {
    const banner = rawCapture ? 0 : BANNER_HEIGHT;
    const maxAvailableHeight = MAX_CANVAS_DIM - banner;
    const maxAvailableWidth = MAX_CANVAS_DIM;

    // Batas skala maksimal yang diizinkan agar seluruh dimensi kanvas <= MAX_CANVAS_DIM
    const maxAllowedScale = Math.min(
        maxAvailableWidth / sourceWidth,
        maxAvailableHeight / sourceHeight,
    );

    // Baseline scale: jika gambar kecil (lebar < 800), coba perbesar ke lebar 800 jika memungkinkan
    let desiredScale = 1;
    if (sourceWidth < 800) {
        desiredScale = 800 / sourceWidth;
    }

    // Skala akhir adalah minimum dari desiredScale dan maxAllowedScale
    const finalScale = Math.min(desiredScale, maxAllowedScale);

    const targetWidth = Math.max(1, Math.round(sourceWidth * finalScale));
    const targetHeight = Math.max(1, Math.round(sourceHeight * finalScale));
    const totalHeight = targetHeight + banner;

    return {
        targetWidth,
        targetHeight,
        bannerHeight: banner,
        totalWidth: targetWidth,
        totalHeight,
    };
}

export function CameraViewfinder({
    title = "Kamera Bukti Lapangan",
    outletName,
    salespersonName = "Petugas",
    defaultCoordinates,
    onCapture,
    onClose,
    rawCapture = false,
    fence,
}: CameraViewfinderProps) {
    const dialogRef = useDialog<HTMLDivElement>(onClose);
    useBackLayer(true, onClose);
    const videoRef = useRef<HTMLVideoElement>(null);
    const streamRef = useRef<MediaStream | null>(null);
    const [cameraActive, setCameraActive] = useState(false);
    const [cameraError, setCameraError] = useState("");
    const [facingMode, setFacingMode] = useState<"environment" | "user">(
        "environment",
    );
    const [restart, setRestart] = useState(0);
    const [hasMultipleCameras, setHasMultipleCameras] = useState(false);
    const [capturing, setCapturing] = useState(false);
    // Pratinjau (DS: Kamera_pratinjau): foto belum dipakai sampai "Gunakan foto".
    const [shot, setShot] = useState<{
        result: CameraCaptureResult;
        url: string;
        elapsed: number;
    }>();

    // Geolocation state
    const [coords, setCoords] = useState<{
        latitude: number;
        longitude: number;
        accuracy: number;
        timestamp: number;
        simulated?: boolean;
    }>(() => ({
        latitude: defaultCoordinates?.latitude ?? 1.487,
        longitude: defaultCoordinates?.longitude ?? 124.8428,
        accuracy: 10,
        timestamp: Date.now(),
        simulated: true,
    }));
    const [gpsStatus, setGpsStatus] = useState<
        "acquiring" | "locked" | "fallback"
    >("acquiring");

    // Real-time clock formatted in WITA (Asia/Makassar)
    const [currentTime, setCurrentTime] = useState("");

    useEffect(() => {
        function updateClock() {
            const now = new Date();
            setCurrentTime(
                new Intl.DateTimeFormat("id-ID", {
                    dateStyle: "medium",
                    timeStyle: "medium",
                    timeZone: "Asia/Makassar",
                }).format(now) + " WITA",
            );
        }
        updateClock();
        const timer = setInterval(updateClock, 1000);
        return () => clearInterval(timer);
    }, []);

    // Track GPS
    useEffect(() => {
        let watchId: number | undefined;
        if ("geolocation" in navigator) {
            navigator.geolocation.getCurrentPosition(
                (pos) => {
                    setCoords({
                        latitude: pos.coords.latitude,
                        longitude: pos.coords.longitude,
                        accuracy: pos.coords.accuracy,
                        timestamp: pos.timestamp,
                        simulated: false,
                    });
                    setGpsStatus("locked");
                },
                () => {
                    setGpsStatus("fallback");
                },
                { enableHighAccuracy: true, timeout: 8000, maximumAge: 10000 },
            );

            watchId = navigator.geolocation.watchPosition(
                (pos) => {
                    setCoords({
                        latitude: pos.coords.latitude,
                        longitude: pos.coords.longitude,
                        accuracy: pos.coords.accuracy,
                        timestamp: pos.timestamp,
                        simulated: false,
                    });
                    setGpsStatus("locked");
                },
                () => {
                    // keep existing coords
                },
                { enableHighAccuracy: true, timeout: 15000, maximumAge: 5000 },
            );
        } else {
            setGpsStatus("fallback");
        }

        return () => {
            if (watchId !== undefined && "geolocation" in navigator) {
                navigator.geolocation.clearWatch(watchId);
            }
        };
    }, []);

    // Check available cameras
    useEffect(() => {
        if (navigator.mediaDevices?.enumerateDevices) {
            navigator.mediaDevices
                .enumerateDevices()
                .then((devices) => {
                    const videoDevices = devices.filter(
                        (d) => d.kind === "videoinput",
                    );
                    setHasMultipleCameras(videoDevices.length > 1);
                })
                .catch(() => {});
        }
    }, []);

    // Start video stream
    useEffect(() => {
        let isCancelled = false;

        async function startStream() {
            setCameraError("");
            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }

            if (!navigator.mediaDevices?.getUserMedia) {
                setCameraError(
                    "Kamera langsung tidak didukung browser ini. Gunakan pemicu kamera perangkat.",
                );
                return;
            }

            try {
                let stream: MediaStream;
                try {
                    stream = await navigator.mediaDevices.getUserMedia({
                        video: {
                            facingMode: { ideal: facingMode },
                            width: { ideal: 1920, min: 640 },
                            height: { ideal: 1080, min: 480 },
                        },
                        audio: false,
                    });
                } catch {
                    // Fallback to basic video constraints
                    stream = await navigator.mediaDevices.getUserMedia({
                        video: true,
                        audio: false,
                    });
                }

                if (isCancelled) {
                    stream.getTracks().forEach((track) => track.stop());
                    return;
                }

                streamRef.current = stream;
                if (videoRef.current) {
                    videoRef.current.srcObject = stream;
                    await videoRef.current.play().catch(() => {});
                }
                setCameraActive(true);
            } catch (err) {
                if (isCancelled) return;
                const message =
                    err instanceof Error ? err.message : String(err);
                if (
                    message.includes("Permission") ||
                    message.includes("denied")
                ) {
                    setCameraError(
                        "Izin kamera ditolak. Berikan izin kamera di pengaturan browser.",
                    );
                } else if (
                    message.includes("NotFound") ||
                    message.includes("Requested device not found") ||
                    message.includes("DevicesNotFoundError")
                ) {
                    setCameraError("Tidak ditemukan perangkat kamera fisik.");
                } else {
                    setCameraError(
                        "Kamera belum dapat dibuka. Tutup aplikasi kamera lain dan coba kembali.",
                    );
                }
                setCameraActive(false);
            }
        }

        void startStream();

        return () => {
            isCancelled = true;
            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }
        };
    }, [facingMode, restart]);

    const outside =
        fence && !coords.simulated
            ? Math.max(
                  0,
                  Math.round(
                      distanceMeters(
                          coords.latitude,
                          coords.longitude,
                          fence.latitude,
                          fence.longitude,
                      ) - fence.radius,
                  ),
              )
            : 0;
    const expired = !!shot && !shot.result.simulated && shot.elapsed > 60;
    function stopAndClose() {
        if (shot) URL.revokeObjectURL(shot.url);
        if (streamRef.current) {
            streamRef.current.getTracks().forEach((track) => track.stop());
            streamRef.current = null;
        }
        onClose();
    }

    async function stampAndExport(
        source: CanvasImageSource,
        sourceWidth: number,
        sourceHeight: number,
    ): Promise<Blob> {
        // Batasi resolusi maksimal 1280px proporsional agar hemat memori & kuota
        const dims = computeWatermarkedDimensions(
            sourceWidth,
            sourceHeight,
            rawCapture,
        );
        const { targetWidth, targetHeight, bannerHeight, totalHeight } = dims;

        const canvas = document.createElement("canvas");
        canvas.width = targetWidth;
        canvas.height = totalHeight;

        const ctx = canvas.getContext("2d");
        if (!ctx) throw new Error("Gagal membuat canvas watermark.");

        // Draw image frame
        ctx.drawImage(source, 0, 0, targetWidth, targetHeight);

        if (!rawCapture) {
            // Watermark Banner Background (Dark FMCG theme)
            ctx.fillStyle = "#0a192f";
            ctx.fillRect(0, targetHeight, targetWidth, bannerHeight);

            // Top accent line in gold/amber
            ctx.fillStyle = "#f59e0b";
            ctx.fillRect(0, targetHeight, targetWidth, 4);

            // Text styling
            ctx.fillStyle = "#ffffff";
            ctx.textBaseline = "middle";

            // Line 1: outlet & document context
            ctx.font =
                "bold 20px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
            const outletText = outletName
                ? `BUKTI DISPLAY · ${outletName}`
                : "BUKTI KUNJUNGAN LAPANGAN";
            ctx.fillText(outletText, 20, targetHeight + 28);

            // Line 2: Timestamp & GPS Coordinates
            ctx.font =
                "16px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
            ctx.fillStyle = "#cbd5e1";
            const timeText =
                currentTime || `${new Date().toLocaleTimeString("id-ID")} WITA`;
            const coordText = `GPS: ${coords.latitude.toFixed(6)}, ${coords.longitude.toFixed(6)} (±${Math.round(coords.accuracy)}m)`;
            ctx.fillText(
                `${timeText}   |   ${coordText}`,
                20,
                targetHeight + 58,
            );

            // Line 3: Officer Name & Verification Badge
            ctx.font =
                "14px -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
            ctx.fillStyle = "#94a3b8";
            const officerText = `Petugas: ${salespersonName}   |   Status: bukti lokal, belum diverifikasi`;
            ctx.fillText(officerText, 20, targetHeight + 86);
        }
        // Convert to Blob
        return new Promise<Blob>((resolve, reject) => {
            canvas.toBlob(
                (blob) => {
                    if (blob) resolve(blob);
                    else
                        reject(
                            new Error("Gagal menghasilkan foto ber-watermark."),
                        );
                },
                "image/jpeg",
                0.8,
            );
        });
    }

    function stage(blob: Blob) {
        const now = Date.now();
        setShot({
            url: URL.createObjectURL(blob),
            elapsed: Math.round((now - coords.timestamp) / 1000),
            result: {
                blob,
                timestamp: now,
                fixTimestamp: coords.timestamp,
                latitude: coords.latitude,
                longitude: coords.longitude,
                accuracy: coords.accuracy,
                simulated: coords.simulated,
            },
        });
        setCapturing(false);
    }
    function retake() {
        if (shot) URL.revokeObjectURL(shot.url);
        setShot(undefined);
        setFacingMode((m) => m); // mulai ulang stream
        setRestart((n) => n + 1);
    }
    async function handleCapture() {
        if (!videoRef.current || capturing) return;
        setCapturing(true);

        try {
            const video = videoRef.current;
            const w = video.videoWidth || 1280;
            const h = video.videoHeight || 720;

            const blob = await stampAndExport(video, w, h);

            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }

            stage(blob);
        } catch (err) {
            setCameraError(
                err instanceof Error ? err.message : "Gagal mengambil foto.",
            );
            setCapturing(false);
        }
    }

    // Direct device camera input fallback handler
    async function handleFallbackFile(file?: File) {
        if (!file) return;
        setCapturing(true);
        try {
            const bitmap = await createImageBitmap(file);
            const blob = await stampAndExport(
                bitmap,
                bitmap.width,
                bitmap.height,
            );
            bitmap.close();

            if (streamRef.current) {
                streamRef.current.getTracks().forEach((track) => track.stop());
                streamRef.current = null;
            }

            stage(blob);
        } catch (err) {
            setCameraError(
                err instanceof Error ? err.message : "Gagal memproses foto.",
            );
            setCapturing(false);
        }
    }

    const stamp = shot ? new Date(shot.result.timestamp) : undefined;
    return (
        <div
            class="cam"
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={title}
        >
            <header class="cam__bar">
                <button
                    type="button"
                    class="cam__close"
                    onClick={stopAndClose}
                    aria-label="Tutup kamera"
                >
                    <Icon name="close" size={24} />
                </button>
                <h2 class="cam__title">{title}</h2>
            </header>
            <div class="cam__view">
                {shot ? (
                    <img
                        class="cam__video"
                        src={shot.url}
                        alt="Pratinjau foto kamera"
                    />
                ) : cameraError ? (
                    <div class="cam__error">
                        <Icon name="warning" size={40} />
                        <p>{cameraError}</p>
                        <label class="ui-btn ui-btn--sec ui-btn--md">
                            <Icon name="camera" size={20} />
                            Buka Kamera Perangkat
                            <input
                                type="file"
                                accept="image/*"
                                capture="environment"
                                style={{ display: "none" }}
                                onChange={(e) =>
                                    void handleFallbackFile(
                                        e.currentTarget.files?.[0],
                                    )
                                }
                            />
                        </label>
                    </div>
                ) : (
                    <video
                        ref={videoRef}
                        class="cam__video"
                        playsinline
                        autoplay
                        muted
                    />
                )}
            </div>
            <div class="cam__panel">
                <div class="cam__stamp" role="status">
                    <strong>
                        {outside && !shot
                            ? `Di luar area · ${outside} m dari batas`
                            : `${shot ? stamp!.toLocaleString("id-ID", { timeZone: "Asia/Makassar" }) : currentTime} · ±${Math.round(
                                  (shot ? shot.result : coords).accuracy,
                              )} m`}
                    </strong>
                    <span>
                        {gpsStatus === "acquiring" && !shot
                            ? "Mencari GPS…"
                            : `${(shot ? shot.result : coords).latitude.toFixed(4)}, ${(shot ? shot.result : coords).longitude.toFixed(4)}${outletName ? ` · ${outletName}` : ""}`}
                        {gpsStatus === "fallback" && !shot
                            ? " · titik simulasi"
                            : ""}
                    </span>
                    <small>Bukti lokal · hash dihitung saat disimpan</small>
                </div>
                {shot ? (
                    <>
                        {expired ? (
                            <div class="cam__note cam__note--warn" role="alert">
                                <Icon name="clock" size={22} />
                                <span>
                                    Foto diambil lebih dari 60 detik setelah
                                    lokasi dikunci (kini {shot.elapsed} detik).
                                    Ambil ulang agar lokasi dan foto cocok.
                                </span>
                            </div>
                        ) : null}
                        <div class="cam__actions">
                            <button
                                type="button"
                                class={`ui-btn ui-btn--md ${expired ? "ui-btn--pri" : "ui-btn--sec"}`}
                                onClick={retake}
                            >
                                <Icon name="camera" size={20} />
                                {expired ? "Ambil ulang" : "Ulangi"}
                            </button>
                            <button
                                type="button"
                                class="ui-btn ui-btn--md ui-btn--pri"
                                disabled={expired}
                                onClick={() => onCapture(shot.result)}
                            >
                                <Icon name="check" size={20} />
                                Gunakan foto
                            </button>
                        </div>
                    </>
                ) : (
                    <>
                        {outside ? (
                            <p class="cam__hint cam__hint--warn" role="status">
                                Di luar area: foto tidak bisa diambil
                            </p>
                        ) : cameraActive && !cameraError ? (
                            <p class="cam__hint">
                                {facingMode === "environment"
                                    ? "Kamera belakang"
                                    : "Kamera depan"}
                                {hasMultipleCameras
                                    ? " · ketuk ikon untuk ganti"
                                    : ""}
                            </p>
                        ) : null}
                        <div class="cam__shutter-row">
                            {cameraActive && !cameraError ? (
                                <button
                                    type="button"
                                    class="cam__shutter"
                                    onClick={() => void handleCapture()}
                                    disabled={capturing || !!outside}
                                    aria-label="Ambil foto bukti"
                                >
                                    <span />
                                </button>
                            ) : null}
                            {hasMultipleCameras &&
                            cameraActive &&
                            !cameraError ? (
                                <button
                                    type="button"
                                    class="cam__flip"
                                    onClick={() =>
                                        setFacingMode((m) =>
                                            m === "environment"
                                                ? "user"
                                                : "environment",
                                        )
                                    }
                                    aria-label="Balik kamera"
                                >
                                    <Icon name="sync" size={22} />
                                </button>
                            ) : null}
                        </div>
                    </>
                )}
            </div>
        </div>
    );
}

import { InteractiveMap } from "./InteractiveMap";
import { useEffect, useState } from "preact/hooks";
import { checkinMap, type MapFix, type MapSite } from "../domain/checkin-map";
import { distanceMeters } from "../domain/format";

// Display-only: this component never authorizes a check-in or changes evidence.
export function CheckinMap({
    site,
    fix,
    compact = false,
}: {
    site: MapSite;
    fix?: MapFix;
    compact?: boolean;
}) {
    const scope = JSON.stringify(site);
    const [enabled, setEnabled] = useState(false);
    const [zoom, setZoom] = useState<number>();
    const [recenter, setRecenter] = useState(0);
    const [failed, setFailed] = useState(false);
    const [ready, setReady] = useState(false);
    useEffect(() => {
        setZoom(undefined);
        setEnabled(false);
        setFailed(false);
        setReady(false);
    }, [scope]);
    let map: ReturnType<typeof checkinMap> | undefined;
    try {
        map = checkinMap(site, fix, zoom);
    } catch {
        /* Keep hook order stable even for corrupt coordinates. */
    }
    const tileKey = map?.tiles.map((t) => t.key).join(",") ?? "";
    useEffect(() => {
        if (!enabled || ready) return;
        const id = setTimeout(() => setFailed(true), 10000);
        return () => clearTimeout(id);
    }, [enabled, tileKey, ready]);
    if (!map)
        return (
            <p role="status">
                Preview peta tidak tersedia: koordinat tujuan/perangkat tidak
                valid.
            </p>
        );
    const distance = fix
        ? distanceMeters(
              site.latitude,
              site.longitude,
              fix.latitude,
              fix.longitude,
          )
        : undefined;
    const status = !fix
        ? "Posisi perangkat belum tersedia"
        : distance! + fix.accuracy <= site.radius
          ? "Di dalam radius"
          : distance! - fix.accuracy > site.radius
            ? "Di luar radius"
            : "Akurasi belum pasti";
    return (
        <section
            class={`checkin-map${compact ? " compact-map" : ""}`}
            aria-label={`Preview peta ${site.name}`}
        >
            <strong>Preview peta · {site.name}</strong>
            {(site.simulated || fix?.simulated) && (
                <p class="map-simulation-label">
                    {site.simulated
                        ? "Titik tujuan simulasi"
                        : "Titik tujuan paket"}
                    {fix?.simulated ? " · posisi simulasi" : ""} · bukan
                    validasi kehadiran resmi.
                </p>
            )}
            <p>
                {status} · Radius {site.radius} m
                {distance !== undefined && (
                    <>
                        {" "}
                        · Jarak {Math.round(distance)} m · Akurasi ±
                        {Math.round(fix!.accuracy)} m
                    </>
                )}
            </p>
            <div class="checkin-map-canvas">
                {enabled && (
                    <InteractiveMap
                        key={scope}
                        site={site}
                        fix={fix}
                        zoom={zoom}
                        recenter={recenter}
                        loading={() => setReady(false)}
                        ready={() => setReady(true)}
                        failed={() => setFailed(true)}
                        changed={setZoom}
                    />
                )}
                <svg
                    hidden={enabled && !failed}
                    viewBox="0 0 512 320"
                    role="img"
                    aria-label="Titik tujuan hijau, posisi perangkat biru, lingkaran radius dan akurasi"
                >
                    <circle
                        cx={map.site.x}
                        cy={map.site.y}
                        r={map.site.radius}
                        fill={status === "Di luar radius" ? "#dc262622" : "#15803d22"}
                        stroke={status === "Di luar radius" ? "#dc2626" : "#15803d"}
                        stroke-width="2"
                    />
                    {fix && (
                        <>
                            <line
                                x1={map.site.x}
                                y1={map.site.y}
                                x2={map.fix.x}
                                y2={map.fix.y}
                                stroke="#334155"
                                stroke-dasharray="5 4"
                            />
                            <circle
                                cx={map.fix.x}
                                cy={map.fix.y}
                                r={map.fix.radius}
                                fill="#2563eb22"
                                stroke="#2563eb"
                                stroke-dasharray="4 3"
                            />
                        </>
                    )}
                    <circle
                        cx={map.site.x}
                        cy={map.site.y}
                        r="7"
                        fill={status === "Di luar radius" ? "#dc2626" : "#15803d"}
                        stroke="white"
                        stroke-width="2"
                    />
                    {fix && (
                        <circle
                            cx={map.fix.x}
                            cy={map.fix.y}
                            r="5"
                            fill="#2563eb"
                            stroke="white"
                            stroke-width="2"
                        />
                    )}
                </svg>
            </div>
            <small>
                Hijau: tujuan · Biru: perangkat. {site.latitude.toFixed(6)},{" "}
                {site.longitude.toFixed(6)}
                {fix && (
                    <>
                        {" "}
                        · Posisi {fix.latitude.toFixed(6)},{" "}
                        {fix.longitude.toFixed(6)}
                    </>
                )}
            </small>
            {!enabled ? (
                <>
                    <p class="footnote">
                        {compact
                            ? "Memuat OpenStreetMap membagikan IP dan area peta."
                            : "Muat peta jalan menghubungi OpenStreetMap dan membagikan area peta serta alamat IP. Foto dan identitas tidak dikirim. Diagram titik tetap tersedia tanpa jaringan."}
                    </p>
                    <button
                        type="button"
                        class="secondary"
                        onClick={() => {
                            setFailed(false);
                            setReady(false);
                            setEnabled(true);
                        }}
                    >
                        Muat peta jalan
                    </button>
                </>
            ) : (
                <>
                    <div class="map-controls">
                        <button
                            type="button"
                            class="secondary"
                            aria-label="Perbesar peta"
                            disabled={map.zoom >= 19}
                            onClick={() => {
                                setFailed(false);
                                setZoom(map.zoom + 1);
                            }}
                        >
                            +
                        </button>
                        <button
                            type="button"
                            class="secondary"
                            aria-label="Perkecil peta"
                            disabled={map.zoom <= 0}
                            onClick={() => {
                                setFailed(false);
                                setZoom(map.zoom - 1);
                            }}
                        >
                            −
                        </button>
                        <button
                            type="button"
                            class="secondary"
                            onClick={() => {
                                setFailed(false);
                                setRecenter((value) => value + 1);
                                setZoom(undefined);
                            }}
                        >
                            Tampilkan kedua titik
                        </button>
                        <button
                            type="button"
                            class="secondary"
                            onClick={() => setEnabled(false)}
                        >
                            Tutup peta jalan
                        </button>
                    </div>
                    {failed ? (
                        <p role="status">
                            Peta jalan gagal atau belum lengkap. Diagram titik
                            tetap tersedia; ini bukan bukti keberhasilan
                            check-in.
                        </p>
                    ) : (
                        !ready && <p role="status">Memuat peta jalan…</p>
                    )}
                </>
            )}
            <small>
                ©{" "}
                <a
                    href="https://www.openstreetmap.org/copyright"
                    target="_blank"
                    rel="noreferrer"
                >
                    OpenStreetMap contributors
                </a>{" "}
                ·{" "}
                <a
                    href="https://www.openstreetmap.org/fixthemap"
                    target="_blank"
                    rel="noreferrer"
                >
                    Laporkan masalah peta
                </a>
            </small>
        </section>
    );
}
